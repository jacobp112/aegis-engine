/*
 * Project Aegis - Kafka Ingress
 * Uses librdkafka to consume ISO 20022 messages and push to RingBuffer.
 *
 * PRODUCTION UPDATE:
 * 1. Removed Hardcoded "Mock XML".
 * 2. Implements real polling structure for RdKafka.
 */

#ifndef KAFKA_INGRESS_HPP
#define KAFKA_INGRESS_HPP

#include "hft_core.hpp"
#include <thread>
#include <iostream>
#include <vector>
#include <string>
#include <librdkafka/rdkafkacpp.h>

class KafkaIngress {
    PaymentRingBuffer& ring_buffer;
    std::thread consumer_thread;
    bool running = false;
    RdKafka::KafkaConsumer* consumer = nullptr;

public:
    KafkaIngress(PaymentRingBuffer& rb) : ring_buffer(rb) {}

    ~KafkaIngress() {
        stop();
        if (consumer) {
            consumer->close();
            delete consumer;
        }
        RdKafka::wait_destroyed(5000);
    }

    void start(const std::string& brokers, const std::string& topic) {
        std::string errstr;

        // 1. Configuration
        RdKafka::Conf* conf = RdKafka::Conf::create(RdKafka::Conf::CONF_GLOBAL);
        if (conf->set("bootstrap.servers", brokers, errstr) != RdKafka::Conf::CONF_OK) {
             std::cerr << "[KAFKA] Config Error: " << errstr << std::endl;
             delete conf;
             return;
        }
        conf->set("group.id", "aegis_group_v1", errstr);
        conf->set("enable.auto.commit", "false", errstr);
        conf->set("auto.offset.reset", "latest", errstr);

        // 2. Create Consumer
        consumer = RdKafka::KafkaConsumer::create(conf, errstr);
        if (!consumer) {
            std::cerr << "[KAFKA] Creation Failed: " << errstr << std::endl;
            delete conf;
            return;
        }
        delete conf;

        // 3. Subscribe
        std::vector<std::string> topics;
        topics.push_back(topic);
        RdKafka::ErrorCode err = consumer->subscribe(topics);
        if (err) {
            std::cerr << "[KAFKA] Subscribe Failed: " << RdKafka::err2str(err) << std::endl;
            return;
        }

        running = true;
        consumer_thread = std::thread(&KafkaIngress::consumer_loop, this);
        std::cout << "[KAFKA] Connected to " << brokers << " | Topic: " << topic << std::endl;
    }

    void stop() {
        running = false;
        if (consumer_thread.joinable()) consumer_thread.join();
    }

private:
    void consumer_loop() {
        if (!consumer) return;

        PaymentData pmt;
        int msg_count = 0;

        while (running && !force_quit) {
            // 2. Poll (Real Blocking Call)
            RdKafka::Message* msg = consumer->consume(100); // 100ms

            switch (msg->err()) {
                case RdKafka::ERR_NO_ERROR: {
                    // 3. Parse Real Data
                    std::string payload(static_cast<const char*>(msg->payload()), msg->len());
                    // Assuming IsoParser is available from hft_core.hpp or similar context
                    if (IsoParser::parse(payload.c_str(), payload.length(), pmt)) {
                         while (!ring_buffer.push(pmt) && running) {
                             // Backpressure
                             std::this_thread::yield();
                         }

                         msg_count++;
                         // Batched Commit (Every 1000 messages)
                         if (msg_count % 1000 == 0) {
                             consumer->commitAsync(NULL);
                         }
                    }
                    break;
                }
                case RdKafka::ERR__TIMED_OUT:
                case RdKafka::ERR__PARTITION_EOF:
                    break;
                default:
                    // Log error (msg->errstr())
                    break;
            }
            delete msg;
        }
    }
};

#endif
