#pragma once

#include "models.hpp"

#include <condition_variable>
#include <functional>
#include <future>
#include <mutex>
#include <pthread.h>
#include <queue>

namespace slang_mcp {
// Slang recursively analyzes expressions. SDK request threads can have small stacks.
class SemanticExecutor {
  public:
    SemanticExecutor();
    ~SemanticExecutor();
    SemanticExecutor(const SemanticExecutor&) = delete;
    SemanticExecutor& operator=(const SemanticExecutor&) = delete;
    [[nodiscard]] Json execute(std::function<Json()> action);

  private:
    pthread_t thread_{};
    std::mutex mutex_;
    std::condition_variable ready_;
    std::queue<std::packaged_task<Json()>> tasks_;
    bool stopping_ = false;
    void run();
    static void* start(void* context);
};
} // namespace slang_mcp
