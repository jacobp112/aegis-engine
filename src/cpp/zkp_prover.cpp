/*
 * Project Aegis - ZKP Prover Service
 * Usage: ./zkp_prover <current_year> <threshold> <birth_year>
 * Output: Proof Hex string
 */

#include "zkp_circuits.hpp"
#include <iostream>
#include <fstream>
#include <string>

int main(int argc, char* argv[]) {
    // 1. Initialize Crypto Subsystem
    try {
        ZkpManager::init();
    } catch (const std::exception& e) {
        std::cerr << "FATAL: Failed to initialize crypto primitives: " << e.what() << std::endl;
        return 1;
    }

    if (argc != 5) {
        std::cerr << "Usage: " << argv[0] << " <pk_path> <current_year> <threshold> <birth_year>" << std::endl;
        return 1;
    }

    std::string pk_path = argv[1];
    long current_year = std::stol(argv[2]);
    long threshold = std::stol(argv[3]);
    long birth_year = std::stol(argv[4]);

    try {
        // 2. Load Proving Key
        auto pk = ZkpManager::load_pk(pk_path);

        // 3. Generate Proof using R1CS Constraints
        std::string proof = ZkpManager::generate_proof(pk, current_year, threshold, birth_year);

        // 3. Output Proof to stdout
        std::cout << proof << std::endl;

    } catch (const std::exception& e) {
        // If age < threshold, constraints are not satisfied, throws error.
        std::cerr << "ERROR: Proof Generation Failed. Reason: " << e.what() << std::endl;
        return 2;
    }

    return 0;
}
