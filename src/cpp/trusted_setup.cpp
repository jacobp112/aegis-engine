/*
 * Project Aegis - Trusted Setup Ceremony (v1.0)
 *
 * Generates the Proving Key (PK) and Verification Key (VK).
 * WARNING: The "Toxic Waste" (randomness) is discarded after this process.
 * In production, this would be a multi-party computation.
 */

#include "zkp_circuits.hpp"
#include <iostream>

int main(int argc, char* argv[]) {
    if (argc != 3) {
        std::cerr << "Usage: trusted_setup <pk_output_path> <vk_output_path>" << std::endl;
        return 1;
    }

    std::string pk_path = argv[1];
    std::string vk_path = argv[2];

    try {
        std::cout << "[SETUP] Initializing Crypto..." << std::endl;
        ZkpManager::init();

        std::cout << "[SETUP] Generating Keys for AgeCheckCircuit..." << std::endl;
        ZkpManager::run_trusted_setup(pk_path, vk_path);

        std::cout << "[SETUP] Success. keys ready." << std::endl;
        return 0;

    } catch (const std::exception& e) {
        std::cerr << "FATAL: " << e.what() << std::endl;
        return 1;
    }
}
