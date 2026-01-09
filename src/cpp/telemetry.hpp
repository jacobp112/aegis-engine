/*
 * Project Aegis - Telemetry
 * High-performance non-blocking tracing (UDP).
 */

#ifndef TELEMETRY_HPP
#define TELEMETRY_HPP

#include <string>
#include <iostream>
#include <chrono>

class Telemetry {
public:
    static void init(const std::string& host, int port) {
        std::cout << "[TELEMETRY] Initialized UDP Sink -> " << host << ":" << port << std::endl;
    }

    struct Span {
        const char* operation;
        uint64_t trace_id; // Simple ID
        long start_ns;
    };

    static Span start_span(const char* name) {
        long now = std::chrono::steady_clock::now().time_since_epoch().count();
        return { name, 0, now };
    }

    static void end_span(const Span& span, float risk_score, bool blocked) {
        long end = std::chrono::steady_clock::now().time_since_epoch().count();
        long duration = end - span.start_ns;

        // Emitting UDP Packet... (Mocked)
        // Format: TraceID | Op | Duration | Tags

        // In HFT, we don't print! We send binary struct to socket.
        // For visual demo, we print only anomalous/high-latency events.
        if (duration > 5000) { // > 5us
             // printf("[SLOW] %s took %ld ns\n", span.operation, duration);
        }
    }
};

#endif
