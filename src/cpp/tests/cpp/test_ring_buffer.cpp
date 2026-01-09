/**
 * Project Aegis - LockFreeRingBuffer Unit Tests
 *
 * Tests the LMAX Disruptor-pattern ring buffer implementation
 * for correctness, thread safety, and memory safety.
 */

#include <gtest/gtest.h>
#include <thread>
#include <vector>
#include <atomic>
#include "../../hft_core.hpp"

// Test fixture for ring buffer tests
class RingBufferTest : public ::testing::Test {
protected:
    // Small buffer for easier testing of edge cases
    LockFreeRingBuffer<int, 8> small_buffer;

    // Larger buffer for concurrent tests
    LockFreeRingBuffer<int, 1024> large_buffer;
};

// =============================================================================
// Basic Functionality Tests
// =============================================================================

TEST_F(RingBufferTest, PushAndPopSingleItem) {
    int value = 42;
    EXPECT_TRUE(small_buffer.push(value));

    int result;
    EXPECT_TRUE(small_buffer.pop(result));
    EXPECT_EQ(result, 42);
}

TEST_F(RingBufferTest, PopFromEmptyBufferReturnsFalse) {
    int result;
    EXPECT_FALSE(small_buffer.pop(result));
}

TEST_F(RingBufferTest, PushToFullBufferReturnsFalse) {
    // Fill buffer (size 8, but can only hold 7 items due to sentinel)
    for (int i = 0; i < 7; ++i) {
        EXPECT_TRUE(small_buffer.push(i)) << "Failed to push item " << i;
    }

    // Next push should fail
    EXPECT_FALSE(small_buffer.push(999));
}

TEST_F(RingBufferTest, IsFullReportsCorrectly) {
    EXPECT_FALSE(small_buffer.is_full());

    // Fill buffer
    for (int i = 0; i < 7; ++i) {
        small_buffer.push(i);
    }

    EXPECT_TRUE(small_buffer.is_full());

    // Pop one item
    int result;
    small_buffer.pop(result);

    EXPECT_FALSE(small_buffer.is_full());
}

TEST_F(RingBufferTest, FIFOOrdering) {
    // Push items in order
    for (int i = 0; i < 5; ++i) {
        small_buffer.push(i);
    }

    // Pop and verify FIFO order
    for (int i = 0; i < 5; ++i) {
        int result;
        EXPECT_TRUE(small_buffer.pop(result));
        EXPECT_EQ(result, i) << "FIFO ordering violated at index " << i;
    }
}

TEST_F(RingBufferTest, WrapAround) {
    // Fill and drain multiple times to test wrap-around
    for (int cycle = 0; cycle < 3; ++cycle) {
        // Fill
        for (int i = 0; i < 7; ++i) {
            EXPECT_TRUE(small_buffer.push(cycle * 100 + i));
        }

        // Drain
        for (int i = 0; i < 7; ++i) {
            int result;
            EXPECT_TRUE(small_buffer.pop(result));
            EXPECT_EQ(result, cycle * 100 + i);
        }
    }
}

// =============================================================================
// Struct/Complex Type Tests
// =============================================================================

TEST(RingBufferPaymentTest, PaymentDataPushPop) {
    LockFreeRingBuffer<PaymentData, 16> payment_buffer;

    PaymentData payment;
    strncpy(payment.debtor_name, "Alice", 63);
    strncpy(payment.creditor_name, "Bob", 63);
    strncpy(payment.currency, "EUR", 3);
    strncpy(payment.uetr, "550e8400-e29b-41d4-a716-446655440000", 36);
    payment.amount = 1000.50;
    payment.valid_schema = true;

    EXPECT_TRUE(payment_buffer.push(payment));

    PaymentData result;
    EXPECT_TRUE(payment_buffer.pop(result));

    EXPECT_STREQ(result.debtor_name, "Alice");
    EXPECT_STREQ(result.creditor_name, "Bob");
    EXPECT_STREQ(result.currency, "EUR");
    EXPECT_DOUBLE_EQ(result.amount, 1000.50);
    EXPECT_TRUE(result.valid_schema);
}

// =============================================================================
// Concurrent Access Tests
// =============================================================================

TEST_F(RingBufferTest, SingleProducerSingleConsumer) {
    const int NUM_ITEMS = 10000;
    std::atomic<int> consumed_sum{0};
    std::atomic<bool> producer_done{false};

    // Producer thread
    std::thread producer([&]() {
        for (int i = 1; i <= NUM_ITEMS; ++i) {
            while (!large_buffer.push(i)) {
                // Spin until space available
                std::this_thread::yield();
            }
        }
        producer_done = true;
    });

    // Consumer thread
    std::thread consumer([&]() {
        int count = 0;
        while (count < NUM_ITEMS) {
            int value;
            if (large_buffer.pop(value)) {
                consumed_sum += value;
                ++count;
            } else if (producer_done) {
                // Producer done, but items may still be in buffer
                std::this_thread::yield();
            }
        }
    });

    producer.join();
    consumer.join();

    // Sum of 1..N = N*(N+1)/2
    int expected_sum = NUM_ITEMS * (NUM_ITEMS + 1) / 2;
    EXPECT_EQ(consumed_sum.load(), expected_sum);
}

TEST_F(RingBufferTest, StressTestHighThroughput) {
    const int NUM_ITEMS = 100000;
    std::atomic<int> items_consumed{0};

    // Producer
    std::thread producer([&]() {
        for (int i = 0; i < NUM_ITEMS; ++i) {
            while (!large_buffer.push(i)) {
                std::this_thread::yield();
            }
        }
    });

    // Consumer
    std::thread consumer([&]() {
        while (items_consumed < NUM_ITEMS) {
            int value;
            if (large_buffer.pop(value)) {
                items_consumed++;
            }
        }
    });

    producer.join();
    consumer.join();

    EXPECT_EQ(items_consumed.load(), NUM_ITEMS);
}

// =============================================================================
// Memory Safety Tests (AddressSanitizer will catch issues)
// =============================================================================

TEST_F(RingBufferTest, NoMemoryLeaksOnRepeatedUse) {
    // This test is primarily for AddressSanitizer validation
    for (int i = 0; i < 10000; ++i) {
        int value = i;
        if (small_buffer.push(value)) {
            int result;
            small_buffer.pop(result);
        }
    }
    // If we get here without ASAN errors, we're good
    SUCCEED();
}

int main(int argc, char **argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
