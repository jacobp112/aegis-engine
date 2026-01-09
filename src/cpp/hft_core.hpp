/*
 * Project Aegis - HFT Core Definitions
 * Shared structures for low-latency modules.
 *
 * UPDATES (v8.1):
 * 1. SimpleTcpClient for Robust IPC (Replacing File SHM).
 * 2. Socket Headers included.
 */

#ifndef HFT_CORE_HPP
#define HFT_CORE_HPP

#include <span>
#include <stdint.h>
#include <atomic>
#include <array>
#include <cstring>
#include <pugixml.hpp>
#include <string_view>
#include <string>

// OS Specific Socket Headers
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #pragma comment(lib, "Ws2_32.lib")
#else
    #include <sys/socket.h>
    #include <arpa/inet.h>
    #include <unistd.h>
    #include <netinet/in.h>
#endif

// --- CONFIGURATION ---
static volatile bool force_quit = false;

// 1. Cache-Line Aligned Entity State (No False Sharing)
struct alignas(64) EntityState {
    std::atomic<uint64_t> last_seen_timestamp; // Nanoseconds epoch
    std::atomic<float> velocity_accumulator;      // Rolling window count
    std::atomic<float> structuring_score;         // Risk accumulation
};

// 2. Lock-Free Ring Buffer (LMAX Disruptor Pattern)
template <typename T, size_t Size>
class LockFreeRingBuffer {
    static_assert((Size & (Size - 1)) == 0, "Size must be power of 2");
    std::atomic<size_t> head{0}; // Written by Producer
    alignas(64) std::atomic<size_t> tail{0}; // Written by Consumer
    std::array<T, Size> buffer;

public:
    bool push(const T& item) {
        size_t current_head = head.load(std::memory_order_relaxed);
        size_t next_head = (current_head + 1) & (Size - 1);

        if (next_head == tail.load(std::memory_order_acquire)) {
            return false; // Full
        }

        buffer[current_head] = item;
        head.store(next_head, std::memory_order_release);
        return true;
    }

    bool pop(T& item) {
        size_t current_tail = tail.load(std::memory_order_relaxed);
        if (current_tail == head.load(std::memory_order_acquire)) {
            return false; // Empty
        }

        item = buffer[current_tail];
        tail.store((current_tail + 1) & (Size - 1), std::memory_order_release);
        return true;
    }

    bool is_full() const {
        size_t current_head = head.load(std::memory_order_relaxed);
        size_t next_head = (current_head + 1) & (Size - 1);
        return next_head == tail.load(std::memory_order_relaxed);
    }
};

// 3. ISO 20022 Data Structure & Parser
struct PaymentData {
    char debtor_name[64];
    char creditor_name[64];
    char currency[4];
    char uetr[37];
    int64_t amount; // Micros (10^-6)
    bool valid_schema;
};

class IsoParser {
public:
    static bool parse(const char* xml, size_t len, PaymentData& out) {
         pugi::xml_document doc;
         pugi::xml_parse_result result = doc.load_buffer(xml, len);
         if (!result) return false;

         // Root: Document -> CstmrCdtTrfinitn -> PmtInf
         pugi::xml_node root = doc.child("Document");
         if (!root) root = doc.first_child();
         if (!root) return false;

         pugi::xml_node cct = root.child("CstmrCdtTrfinitn");
         if (!cct) {
             cct = root.child("FIToFICdtTrf"); // Handle multiple pacs variants
             if (!cct) return false;
         }

         pugi::xml_node pmt_inf = cct.child("PmtInf");
         if (!pmt_inf) pmt_inf = cct.child("CdtTrfTxInf");
         if (!pmt_inf) return false;

         pugi::xml_node pmt_id = pmt_inf.child("PmtId");
         if (!pmt_id) return false;
         pugi::xml_node uetr_node = pmt_id.child("UETR");
         if (!uetr_node) uetr_node = pmt_id.child("EndToEndId");
         if (!uetr_node) return false;

         strncpy(out.uetr, uetr_node.text().as_string(), 36);
         out.uetr[36] = '\0';

         pugi::xml_node dbtr_nm = pmt_inf.child("Dbtr").child("Nm");
         pugi::xml_node cdtr_nm = pmt_inf.child("Cdtr").child("Nm");

         if (!dbtr_nm || !cdtr_nm) return false;

         strncpy(out.debtor_name, dbtr_nm.text().as_string(), 63);
         out.debtor_name[63] = '\0';

         strncpy(out.creditor_name, cdtr_nm.text().as_string(), 63);
         out.creditor_name[63] = '\0';

         pugi::xml_node amt_node = pmt_inf.child("Amt").child("InstdAmt");
         if (!amt_node) return false;

         const char* ccy = amt_node.attribute("Ccy").value();
         if (!ccy || strlen(ccy) != 3) return false;

         if (strcmp(ccy, "EUR") != 0 && strcmp(ccy, "USD") != 0 && strcmp(ccy, "GBP") != 0) {
             return false;
         }

         strncpy(out.currency, ccy, 3);
         out.currency[3] = '\0';

         // Safe String Parsing (No FPU)
         const char* amt_str = amt_node.text().as_string();
         if (!amt_str || *amt_str == '\0') return false;

         int64_t integrals = 0;
         int64_t fractionals = 0;
         int64_t sign = 1;

         const char* p = amt_str;
         if (*p == '-') { sign = -1; p++; }

         // Parse Integral Part
         while (*p >= '0' && *p <= '9') {
             integrals = (integrals * 10) + (*p - '0');
             p++;
         }

         // Parse Fractional Part (Micros = 6 digits)
         if (*p == '.') {
             p++;
             int digits = 0;
             while (*p >= '0' && *p <= '9' && digits < 6) {
                 fractionals = (fractionals * 10) + (*p - '0');
                 p++;
                 digits++;
             }
             // Pad if fewer than 6 digits (e.g., 0.5 -> 500000)
             while (digits < 6) {
                 fractionals *= 10;
                 digits++;
             }
         }

         out.amount = sign * (integrals * 1000000 + fractionals);

         if (out.amount <= 0) return false;

         out.valid_schema = true;
         return true;
    }
};

// 4. Simple TCP Client for IPC (Robust Bridge)
class SimpleTcpClient {
    int sock = -1;
    struct sockaddr_in serv_addr;
#ifdef _WIN32
    WSADATA wsaData;
#endif

public:
    bool connect(const char* host, int port) {
#ifdef _WIN32
        WSAStartup(MAKEWORD(2, 2), &wsaData);
#endif
        if ((sock = socket(AF_INET, SOCK_STREAM, 0)) < 0) {
            return false;
        }

        serv_addr.sin_family = AF_INET;
        serv_addr.sin_port = htons(port);

        if (inet_pton(AF_INET, host, &serv_addr.sin_addr) <= 0) {
             return false;
        }

        if (::connect(sock, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) < 0) {
            return false;
        }
        return true;
    }

    void send_json(const std::string& json_payload) {
        if (sock < 0) return;

        uint32_t len = htonl(json_payload.size());
        ::send(sock, (const char*)&len, 4, 0);
        ::send(sock, json_payload.c_str(), json_payload.size(), 0);
    }

    void close() {
#ifdef _WIN32
        if (sock >= 0) closesocket(sock);
        WSACleanup();
#else
        if (sock >= 0) ::close(sock);
#endif
    }
};

using PaymentRingBuffer = LockFreeRingBuffer<PaymentData, 16384>;

#endif
