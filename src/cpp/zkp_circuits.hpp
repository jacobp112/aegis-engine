/*
 * Project Aegis - Zero Knowledge Circuits (Production Grade)
 * Implementation: libsnark (Gadgetlib) - R1CS
 *
 * STRICT MODE: Real Constraints Enabled.
 */

#ifndef ZKP_CIRCUITS_HPP
#define ZKP_CIRCUITS_HPP

#include <iostream>
#include <string>
#include <sstream>
#include <fstream>
#include <vector>
#include <stdexcept>

// Essential libsnark headers
#include <libsnark/gadgetlib/gadget.hpp>
#include <libsnark/gadgetlib/protoboard.hpp>
#include <libsnark/common/default_types/r1cs_ppzksnark_pp.hpp>
#include <libsnark/zk_proof_systems/ppzksnark/r1cs_ppzksnark/r1cs_ppzksnark.hpp>
#include <libsnark/gadgetlib/gadgets/basic_gadgets.hpp> // comparison_gadget
#include <libff/common/utils.hpp>

using namespace libsnark;
using namespace libff;

// Circuit: Age Integrity Check
// Proves: (CurrentYear - BirthYear) >= Threshold
class AgeCheckCircuit : public gadget<FieldT> {
public:
    pb_variable<FieldT> current_year;
    pb_variable<FieldT> birth_year; // Private
    pb_variable<FieldT> threshold;
    pb_variable<FieldT> age;
    pb_variable<FieldT> is_adult;

    // Internal Gadgets
    pb_variable<FieldT> less;
    pb_variable<FieldT> less_or_eq;
    std::shared_ptr<comparison_gadget<FieldT>> cmp;

    AgeCheckCircuit(protoboard<FieldT>& pb,
                    const pb_variable<FieldT>& curr,
                    const pb_variable<FieldT>& birth,
                    const pb_variable<FieldT>& thresh)
        : gadget<FieldT>(pb, "AgeCheck"),
          current_year(curr), birth_year(birth), threshold(thresh) {
        age.allocate(pb, "age");
        is_adult.allocate(pb, "is_adult");

        less.allocate(pb, "less");
        less_or_eq.allocate(pb, "less_or_eq");

        // Setup comparison: threshold <= age ?
        // Effectively checking if age < threshold is false (meaning age >= threshold)
        // We use comparison_gadget to check: threshold <= age
        // n = 64 bits typical
        cmp.reset(new comparison_gadget<FieldT>(pb, 64, threshold, age, less, less_or_eq, "cmp"));
    }

    void generate_r1cs_constraints() {
        // 1. age = current_year - birth_year
        this->pb.add_r1cs_constraint(
            r1cs_constraint<FieldT>(current_year - birth_year, 1, age),
            "age_calculation"
        );

        // 2. Enforce logic: threshold <= age
        // The comparison gadget generates constraints that enforce 'less' and 'less_or_eq' variables
        // based on the values of 'threshold' and 'age'.
        cmp->generate_r1cs_constraints();

        // 3. Bind result to is_adult
        // if is_adult == 1, then less_or_eq MUST be 1.
        // We want to prove that the USER IS AN ADULT.
        // So we constrain: is_adult * 1 = less_or_eq
        this->pb.add_r1cs_constraint(
            r1cs_constraint<FieldT>(is_adult, 1, less_or_eq),
            "bind_is_adult_to_comparison"
        );

        // 4. Force public output to be TRUE (1)
        // This ensures a proof can ONLY be generated if the user IS an adult.
        // The verifier checks that 'is_adult' (if public) is 1, or implicitly the circuit requires satisfied constraints.
        // Usually, is_adult might be public input, or we just enforce the check inside checks.
        // If we want the proof to imply "Validity", we constrain is_adult to 1.
        this->pb.add_r1cs_constraint(
            r1cs_constraint<FieldT>(is_adult, 1, FieldT::one()),
            "must_be_adult"
        );
    }

    void generate_witness(long curr_val, long birth_val, long thresh_val) {
        this->pb.val(current_year) = curr_val;
        this->pb.val(birth_year) = birth_val;
        this->pb.val(threshold) = thresh_val;

        long age_val = curr_val - birth_val;
        this->pb.val(age) = age_val;

        // Fill gadget witness
        cmp->generate_witness();

        // less_or_eq calculation matches the gadget logic: (A <= B)
        bool is_le = (thresh_val <= age_val);
        this->pb.val(is_adult) = is_le ? 1 : 0;
    }
};

class ZkpManager {
public:
    using PP = default_r1cs_ppzksnark_pp;
    using PK = r1cs_ppzksnark_proving_key<PP>;
    using VK = r1cs_ppzksnark_verification_key<PP>;
    using Proof = r1cs_ppzksnark_proof<PP>;

    static void init() {
        PP::init_public_params();
    }

    // --- PHASE 2: TRUSTED SETUP ---
    static void run_trusted_setup(const std::string& pk_path, const std::string& vk_path) {
        protoboard<FieldT> pb;

        // ALLOCATION ORDER MATTERS FOR PUBLIC INPUTS
        // Public: CurrentYear, Threshold
        // Private: BirthYear
        pb_variable<FieldT> curr, thresh, birth;

        curr.allocate(pb, "current_year"); // Index 1
        thresh.allocate(pb, "threshold");  // Index 2
        birth.allocate(pb, "birth_year");  // Index 3 (Private)

        pb.set_input_sizes(2); // First 2 variables are PRIMARY (Public)

        AgeCheckCircuit circuit(pb, curr, birth, thresh);
        circuit.generate_r1cs_constraints();

        const r1cs_constraint_system<FieldT> constraint_system = pb.get_constraint_system();
        r1cs_ppzksnark_keypair<PP> keypair = r1cs_ppzksnark_generator<PP>(constraint_system);

        // Serialize
        std::ofstream pk_file(pk_path, std::ios::binary);
        if (!pk_file) throw std::runtime_error("Write failed: " + pk_path);
        pk_file << keypair.pk;

        std::ofstream vk_file(vk_path, std::ios::binary);
        if (!vk_file) throw std::runtime_error("Write failed: " + vk_path);
        vk_file << keypair.vk;

        std::cout << "[ZKP] Trusted Setup Complete. Keys saved to disk." << std::endl;
    }

    static PK load_pk(const std::string& path) {
        PK pk;
        std::ifstream file(path, std::ios::binary);
        if (!file) throw std::runtime_error("Missing Proving Key: " + path);
        file >> pk;
        return pk;
    }

    static VK load_vk(const std::string& path) {
        VK vk;
        std::ifstream file(path, std::ios::binary);
        if (!file) throw std::runtime_error("Missing Verification Key: " + path);
        file >> vk;
        return vk;
    }

    // --- PROVER ---
    static std::string generate_proof(const PK& pk, long current_year, long threshold, long birth_year) {
        protoboard<FieldT> pb;
        pb_variable<FieldT> curr, thresh, birth;

        // Exact same allocation order
        curr.allocate(pb, "current_year");
        thresh.allocate(pb, "threshold");
        birth.allocate(pb, "birth_year");

        pb.set_input_sizes(2);

        AgeCheckCircuit circuit(pb, curr, birth, thresh);
        circuit.generate_r1cs_constraints();
        circuit.generate_witness(current_year, birth_year, threshold);

        if (!pb.is_satisfied()) {
             throw std::runtime_error("Constraint Failure: Inputs invalid (Underage or bad math).");
        }

        Proof proof = r1cs_ppzksnark_prover<PP>(pk, pb.primary_input(), pb.auxiliary_input());

        std::stringstream ss;
        ss << proof;
        return ss.str();
    }

    // --- VERIFIER (REAL) ---
    static bool verify_proof(const VK& vk, const std::string& proof_str, long current_year, long threshold) {
        Proof proof;
        std::stringstream ss(proof_str);
        ss >> proof;

        // Construct Public Inputs
        // Must match the primary_input vector from the Prover.
        std::vector<FieldT> primary_input;
        primary_input.push_back(FieldT(current_year));
        primary_input.push_back(FieldT(threshold));

        return r1cs_ppzksnark_verifier_strong_IC<PP>(vk, primary_input, proof);
    }
};

#endif
