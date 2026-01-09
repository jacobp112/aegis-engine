/*
 * Project Aegis - Prometheus Metrics
 * High-performance metrics for observability.
 *
 * Exposes metrics via HTTP /metrics endpoint for Prometheus scraping
 * or can push to a PushGateway.
 *
 * Metrics Exported:
 * - aegis_ingress_tps: Transactions per second entering the system
 * - aegis_ring_buffer_usage: Ring buffer utilization (0.0 - 1.0)
 * - aegis_transactions_total: Total transactions processed (Counter)
 * - aegis_risk_blocks_total: Total transactions blocked (Counter)
 */

#ifndef METRICS_HPP
#define METRICS_HPP

#include <atomic>
#include <chrono>
#include <string>
#include <sstream>
#include <thread>
#include <mutex>
#include <cstdio>

#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #pragma comment(lib, "Ws2_32.lib")
#else
    #include <sys/socket.h>
    #include <netinet/in.h>
    #include <arpa/inet.h>
    #include <unistd.h>
#endif

namespace Metrics {

// =============================================================================
// Atomic Counters & Gauges (Lock-Free)
// =============================================================================

// Counters (monotonic increasing)
static std::atomic<uint64_t> g_transactions_total{0};
static std::atomic<uint64_t> g_risk_blocks_total{0};
static std::atomic<uint64_t> g_drops_total{0};

// Gauges (point-in-time values)
static std::atomic<double> g_ring_buffer_usage{0.0};
static std::atomic<double> g_ingress_tps{0.0};

// Internal: for TPS calculation
static std::atomic<uint64_t> g_tx_count_window{0};
static std::atomic<uint64_t> g_last_tps_calc_time{0};

// =============================================================================
// Metric Recording Functions (Hot Path - Must be Fast)
// =============================================================================

inline void record_transaction() {
    g_transactions_total.fetch_add(1, std::memory_order_relaxed);
    g_tx_count_window.fetch_add(1, std::memory_order_relaxed);
}

inline void record_block() {
    g_risk_blocks_total.fetch_add(1, std::memory_order_relaxed);
}

inline void record_drop() {
    g_drops_total.fetch_add(1, std::memory_order_relaxed);
}

inline void update_ring_buffer_usage(size_t current_size, size_t max_size) {
    double usage = (max_size > 0) ? static_cast<double>(current_size) / max_size : 0.0;
    g_ring_buffer_usage.store(usage, std::memory_order_relaxed);
}

// =============================================================================
// TPS Calculator (Called Periodically)
// =============================================================================

inline void calculate_tps() {
    using namespace std::chrono;

    uint64_t now_ms = duration_cast<milliseconds>(
        steady_clock::now().time_since_epoch()
    ).count();

    uint64_t last_time = g_last_tps_calc_time.load(std::memory_order_relaxed);

    if (last_time == 0) {
        g_last_tps_calc_time.store(now_ms, std::memory_order_relaxed);
        return;
    }

    uint64_t elapsed_ms = now_ms - last_time;
    if (elapsed_ms >= 1000) { // Calculate every second
        uint64_t count = g_tx_count_window.exchange(0, std::memory_order_relaxed);
        double tps = static_cast<double>(count) * 1000.0 / elapsed_ms;
        g_ingress_tps.store(tps, std::memory_order_relaxed);
        g_last_tps_calc_time.store(now_ms, std::memory_order_relaxed);
    }
}

// =============================================================================
// Prometheus Format Export
// =============================================================================

inline std::string export_prometheus() {
    std::ostringstream out;

    // HELP and TYPE declarations
    out << "# HELP aegis_ingress_tps Transactions per second entering the system\n";
    out << "# TYPE aegis_ingress_tps gauge\n";
    out << "aegis_ingress_tps " << g_ingress_tps.load(std::memory_order_relaxed) << "\n\n";

    out << "# HELP aegis_ring_buffer_usage Ring buffer utilization ratio (0-1)\n";
    out << "# TYPE aegis_ring_buffer_usage gauge\n";
    out << "aegis_ring_buffer_usage " << g_ring_buffer_usage.load(std::memory_order_relaxed) << "\n\n";

    out << "# HELP aegis_transactions_total Total transactions processed\n";
    out << "# TYPE aegis_transactions_total counter\n";
    out << "aegis_transactions_total " << g_transactions_total.load(std::memory_order_relaxed) << "\n\n";

    out << "# HELP aegis_risk_blocks_total Total transactions blocked due to high risk\n";
    out << "# TYPE aegis_risk_blocks_total counter\n";
    out << "aegis_risk_blocks_total " << g_risk_blocks_total.load(std::memory_order_relaxed) << "\n\n";

    out << "# HELP aegis_drops_total Total messages dropped due to backpressure\n";
    out << "# TYPE aegis_drops_total counter\n";
    out << "aegis_drops_total " << g_drops_total.load(std::memory_order_relaxed) << "\n";

    return out.str();
}

// =============================================================================
// Minimal HTTP Server for /metrics Endpoint
// =============================================================================

class MetricsServer {
    int server_fd = -1;
    std::thread server_thread;
    std::atomic<bool> running{false};
    int port;

public:
    MetricsServer(int p = 9090) : port(p) {}

    void start() {
        if (running) return;
        running = true;
        server_thread = std::thread(&MetricsServer::serve, this);
        printf("[METRICS] Prometheus endpoint started on port %d\n", port);
    }

    void stop() {
        running = false;
        if (server_fd >= 0) {
#ifdef _WIN32
            closesocket(server_fd);
            WSACleanup();
#else
            close(server_fd);
#endif
        }
        if (server_thread.joinable()) {
            server_thread.join();
        }
    }

    ~MetricsServer() { stop(); }

private:
    void serve() {
#ifdef _WIN32
        WSADATA wsaData;
        WSAStartup(MAKEWORD(2, 2), &wsaData);
#endif

        server_fd = socket(AF_INET, SOCK_STREAM, 0);
        if (server_fd < 0) {
            printf("[METRICS] Failed to create socket\n");
            return;
        }

        // Reuse address
        int opt = 1;
#ifdef _WIN32
        setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, (const char*)&opt, sizeof(opt));
#else
        setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
#endif

        struct sockaddr_in addr;
        addr.sin_family = AF_INET;
        addr.sin_addr.s_addr = INADDR_ANY;
        addr.sin_port = htons(port);

        if (bind(server_fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            printf("[METRICS] Failed to bind port %d\n", port);
            return;
        }

        listen(server_fd, 5);

        while (running) {
            // Accept with timeout for graceful shutdown
            struct timeval tv;
            tv.tv_sec = 1;
            tv.tv_usec = 0;

            fd_set fds;
            FD_ZERO(&fds);
            FD_SET(server_fd, &fds);

            if (select(server_fd + 1, &fds, NULL, NULL, &tv) <= 0) {
                continue;
            }

            struct sockaddr_in client_addr;
            socklen_t client_len = sizeof(client_addr);
            int client_fd = accept(server_fd, (struct sockaddr*)&client_addr, &client_len);

            if (client_fd < 0) continue;

            // Read request (we don't really parse it, just serve /metrics)
            char buffer[1024];
            recv(client_fd, buffer, sizeof(buffer) - 1, 0);

            // Update TPS before serving
            calculate_tps();

            // Generate response
            std::string body = export_prometheus();
            std::ostringstream response;
            response << "HTTP/1.1 200 OK\r\n";
            response << "Content-Type: text/plain; charset=utf-8\r\n";
            response << "Content-Length: " << body.size() << "\r\n";
            response << "\r\n";
            response << body;

            std::string resp_str = response.str();
            send(client_fd, resp_str.c_str(), resp_str.size(), 0);

#ifdef _WIN32
            closesocket(client_fd);
#else
            close(client_fd);
#endif
        }
    }
};

// Global server instance
static MetricsServer g_metrics_server;

inline void init(int port = 9090) {
    g_metrics_server = MetricsServer(port);
    g_metrics_server.start();
}

inline void shutdown() {
    g_metrics_server.stop();
}

} // namespace Metrics

#endif // METRICS_HPP
