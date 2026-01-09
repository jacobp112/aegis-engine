/*
 * Project Aegis - Fast Risk Engine
 * Deterministic Inference with Hot-Swappable Rules.
 *
 * ENTERPRISE REFACTOR (v8.1 - High Performance):
 * 1. Standard Library Containers (std::unordered_map).
 * 2. SHARDED LOCKING (1024 Mutexes) - Solves Global Lock Bottleneck.
 * 3. False Sharing Prevention (Padding).
 */

#ifndef RISK_ENGINE_HPP
#define RISK_ENGINE_HPP

#include "hft_core.hpp"
#include <atomic>
#include <fstream>
#include <iostream>
#include <chrono>
#include <unordered_map>
#include <mutex>
#include <string>
#include <array>

// --- MOCK EXTERNAL STORAGE (Redis/Ignite) ---
class DistrubutedCache {
public:
    static EntityState fetch_from_redis(const std::string& key) {
        return EntityState();
    }
};

struct ModelWeights {
    float velocity_weight;
    float structuring_weight;
    float velocity_threshold;
    float structuring_threshold;
    float baseline;
};

// SHARDING CONFIG
// 1024 Shards allows huge concurrency.
// Power of 2 for fast modulus.
constexpr size_t RISK_MAP_SHARDS = 1024;

class FastRiskEngine {
public:
    // SHARD STRUCTURE
    // Align to 64 bytes to prevent "False Sharing" of mutexes on adjacent cache lines.
    struct alignas(64) RiskShard {
        std::mutex mtx;
        std::unordered_map<std::string, EntityState> map;
        // Padding is implicit due to alignas(64), but ensures each mutex is on its own line.
    };

    std::array<RiskShard, RISK_MAP_SHARDS> shards;

    // TIER 2: LIMITS (Per Shard approx)
    static constexpr size_t MAX_ENTRIES_PER_SHARD = 500; // 500 * 1024 = 512k Total

    // Double Buffered Rules
    ModelWeights rule_sets[2];
    std::atomic<int> active_idx{0};

    FastRiskEngine() {
        // Reserve per shard
        for(auto& shard : shards) {
            shard.map.reserve(MAX_ENTRIES_PER_SHARD);
        }

        rule_sets[0] = {0.6f, 0.25f, 5.0f, 9000.0f, 0.05f};
        rule_sets[1] = {0.6f, 0.25f, 5.0f, 9000.0f, 0.05f};
    }

    void reload_rules(const char* json_path) {
        int next_idx = !active_idx.load();
        rule_sets[next_idx] = {0.8f, 0.1f, 3.0f, 8000.0f, 0.05f};
        active_idx.store(next_idx, std::memory_order_release);
    }

    struct RiskResult {
        float score;
        bool is_blocked;
    };

    // FNV1a Hash for Shard Selection (Wait-Free)
    static constexpr uint64_t fnv1a_hash(const char* str, size_t len) {
        uint64_t hash = 14695981039346656037ULL;
        for (size_t i = 0; i < len; ++i) {
            hash ^= static_cast<unsigned char>(str[i]);
            hash *= 1099511628211ULL;
        }
        return hash;
    }

    RiskResult evaluate(const char* entity_name, size_t name_len, int64_t amount) {
        // 1. Select Shard
        uint64_t h = fnv1a_hash(entity_name, name_len);
        size_t shard_idx = h & (RISK_MAP_SHARDS - 1);
        RiskShard& shard = shards[shard_idx];

        std::string key(entity_name, name_len);

        // 2. Load Rules (Atomic)
        int idx = active_idx.load(std::memory_order_acquire);
        const ModelWeights& w = rule_sets[idx];

        // 3. Lock ONLY the Shard
        std::unique_lock<std::mutex> lock(shard.mtx);

        auto& risk_map = shard.map;
        auto it = risk_map.find(key);

        if (it == risk_map.end()) {
            if (risk_map.size() >= MAX_ENTRIES_PER_SHARD) {
                // Tiered Storage Logic (Mocked)
                // Just proceed for now to avoid complexity in this demo file
            }

            EntityState cold_state = DistrubutedCache::fetch_from_redis(key);
            it = risk_map.emplace(key, cold_state).first;
        }

        EntityState& state = it->second;

        // 4. Update Logic (Inside Shard Lock)
        long now_ns = std::chrono::steady_clock::now().time_since_epoch().count();
        uint64_t last_seen = state.last_seen_timestamp.load(std::memory_order_relaxed);

        if ((now_ns - last_seen) > 1000000000ULL) {
             state.velocity_accumulator.store(0.0f, std::memory_order_relaxed);
        }

        state.last_seen_timestamp.store(now_ns, std::memory_order_relaxed);
        float v = state.velocity_accumulator.load(std::memory_order_relaxed);
        v += 1.0f;
        state.velocity_accumulator.store(v, std::memory_order_relaxed);

        lock.unlock(); // Release lock quickly

        // 5. Inference (Wait-Free math)
        float velocity_score = (v > w.velocity_threshold * 2) ? 1.0f : (v / (w.velocity_threshold * 2));
        float structuring_score = 0.0f;
        // Structuring Check (Micros comparisons)
        // Thresholds are floats in config, so we scale them up to micros.
        int64_t threshold_micros = (int64_t)(w.structuring_threshold * 1000000.0f);
        int64_t limit_micros = 10000 * 1000000LL;

        if (amount >= threshold_micros && amount < limit_micros) {
            structuring_score = 1.0f;
        }

        float total_risk = w.baseline
                         + (velocity_score * w.velocity_weight)
                         + (structuring_score * w.structuring_weight);

        if (total_risk > 1.0f) total_risk = 1.0f;

        return { total_risk, (total_risk > 0.8f) };
    }
};

#endif
