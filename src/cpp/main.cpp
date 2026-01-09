/*
 * Project Aegis - Enterprise Matching Engine (v8.2 - Production)
 *
 * CORE STANDARDS:
 * 1. XML PARSING: pugixml (Standard)
 * 2. CRYPTO: libsnark (ZKP)
 * 3. LOGGING: OpenTelemetry (UDP)
 * 4. INFERENCE: C++ Hot Path (Latency < 1us)
 * 5. IPC: ZeroMQ (Industry Standard)
 */

#include "hft_core.hpp"
#include "risk_engine.hpp"
#include "kafka_ingress.hpp"
#include "telemetry.hpp"
#include "rules_loader.hpp"
#include "metrics.hpp"
#include <fstream>
#include <iostream>
#include <thread>
#include <vector>
#include <string>

#include <zmq.hpp>

// Global Instances
static FastRiskEngine g_risk_engine;
static PaymentRingBuffer g_ring_buffer; // 16K slots

// TELEMETRY/IPC
struct IpcMessage {
    char data[512];
    size_t len;
};

using IpcRingBuffer = LockFreeRingBuffer<IpcMessage, 4096>;
static IpcRingBuffer g_ipc_buffer;

// --- IPC SENDER THREAD ---
void ipc_sender_worker() {
    printf("[IPC] ZeroMQ Sender Thread Started.\n");

    zmq::context_t ctx;
    zmq::socket_t sock(ctx, zmq::socket_type::push);

    try {
        sock.connect("tcp://127.0.0.1:5555");
        printf("[IPC] Bound to ZMQ Endpoint.\n");
    } catch (const zmq::error_t& e) {
        printf("[IPC] ZMQ Init Failed: %s\n", e.what());
        return;
    }

    while (!force_quit) {
        IpcMessage msg;
        // Drain buffer
        while (g_ipc_buffer.pop(msg)) {
            try {
                // Zero-Copy send using buffer view
                sock.send(zmq::buffer(msg.data, msg.len), zmq::send_flags::dontwait);
            } catch (const zmq::error_t& e) {
                // Silently drop or log if needed
            }
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    sock.close();
    ctx.close();
}

// --- WORKER ---
void risk_worker() {
    printf("[WORKER] Risk Engine On-Line. Core Affine.\n");
    PaymentData item;

    while (!force_quit) {
        // Wait-Free Consumer
        while (g_ring_buffer.pop(item)) {
            // METRICS: Record transaction
            Metrics::record_transaction();

            auto span = Telemetry::start_span("risk_check");

            FastRiskEngine::RiskResult risk = g_risk_engine.evaluate(item.debtor_name, strlen(item.debtor_name), item.amount);

            Telemetry::end_span(span, risk.score, risk.is_blocked);

            if (risk.is_blocked) {
                 // METRICS: Record block
                 Metrics::record_block();
                 printf("[RISK] Target: %s | Score: %.4f | Blocked: YES\n",
                   item.debtor_name, risk.score);
             }

             // ASYNC PUSH (Non-Blocking)
             if (risk.score > 0.5) {
                 IpcMessage msg;
                 int len = snprintf(msg.data, 512,
                     // Integer-based string formatting (Micros -> Decimal String)
                     "{ \"debtor\": \"%s\", \"amount\": %lld.%06lld, \"uetr\": \"%s\" }",
                     item.debtor_name, (long long)(item.amount / 1000000), (long long)(std::abs(item.amount % 1000000)), item.uetr
                  );
                 if (len > 0 && len < 512) {
                     msg.len = len;
                     if (!g_ipc_buffer.push(msg)) {
                         // METRICS: Record drop due to backpressure
                         Metrics::record_drop();
                     }
                 }
             }
        }

        // METRICS: Update ring buffer usage and TPS periodically
        Metrics::calculate_tps();

        std::this_thread::yield();
    }
}

// --- FILE INGRESS (REPLAY MODE) ---
class FileIngress {
    PaymentRingBuffer& ring_buffer;
public:
    FileIngress(PaymentRingBuffer& rb) : ring_buffer(rb) {}

    void run(const std::string& filepath) {
        printf("[REPLAY] Reading logs from %s...\n", filepath.c_str());
        std::ifstream infile(filepath, std::ios::binary);
        if (!infile) {
            printf("[REPLAY] Error: File not found.\n");
            return;
        }

        std::string line;
        while (std::getline(infile, line) && !force_quit) {
            PaymentData pmt;
            if (IsoParser::parse(line.c_str(), line.length(), pmt)) {
                 while (!ring_buffer.push(pmt) && !force_quit) {
                     std::this_thread::yield();
                 }
            }
        }
        printf("[REPLAY] Finished.\n");
    }
};

int main(int argc, char *argv[]) {
    std::cout << "============================================" << std::endl;
    std::cout << "   PROJECT AEGIS - HFT COMPLIANCE ENGINE    " << std::endl;
    std::cout << "============================================" << std::endl;

    bool replay_mode = false;
    std::string replay_file;

    for (int i=1; i<argc; i++) {
        if (std::string(argv[i]) == "--replay-mode" && i+1 < argc) {
            replay_mode = true;
            replay_file = argv[i+1];
        }
    }

    // 1. Setup Telemetry
    Telemetry::init("127.0.0.1", 6831);

    // 1b. Setup Prometheus Metrics Server (port 9090)
    Metrics::init(9090);

    // 2. Rules Loader
    RulesLoader rules_loader(g_risk_engine);
    rules_loader.start("model_weights.json");

    // 3a. Start IPC Thread (ZMQ)
    std::thread ipc_thread(ipc_sender_worker);
    ipc_thread.detach();

    // 3b. Start Worker
    std::thread worker(risk_worker);
    worker.detach();

    if (replay_mode) {
        FileIngress ingress(g_ring_buffer);
        ingress.run(replay_file);
        std::this_thread::sleep_for(std::chrono::seconds(2));
    } else {
        KafkaIngress ingress(g_ring_buffer);
        ingress.start("kafka-broker:9092", "transactions.euro.v1");
        std::this_thread::sleep_for(std::chrono::seconds(5));
        ingress.stop();
    }

    force_quit = true;
    rules_loader.stop();
    Metrics::shutdown();
    printf("[ENGINE] Shutdown.\n");
    return 0;
}
