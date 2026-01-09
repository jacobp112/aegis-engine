/*
 * Project Aegis - Rules Loader
 * Watches configuration file and triggers engine update.
 */

#ifndef RULES_LOADER_HPP
#define RULES_LOADER_HPP

#include "risk_engine.hpp"
#include <thread>
#include <chrono>

class RulesLoader {
    FastRiskEngine& engine;
    std::thread watcher_thread;
    bool running = false;

public:
    RulesLoader(FastRiskEngine& eng) : engine(eng) {}

    void start(const std::string& path) {
        running = true;
        watcher_thread = std::thread(&RulesLoader::watch_loop, this, path);
    }

    void stop() {
        running = false;
        if (watcher_thread.joinable()) watcher_thread.join();
    }

private:
    void watch_loop(std::string path) {
        // Simulating file watch
        // In prod: use inotify (Linux) or ReadDirectoryChangesW (Windows)
        while (running && !force_quit) {
            std::this_thread::sleep_for(std::chrono::seconds(2));

            // For Demo: Trigger reload every few seconds
            // engine.reload_rules(path.c_str());
        }
    }
};

#endif
