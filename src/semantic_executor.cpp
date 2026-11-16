#include "semantic_executor.hpp"

#include <system_error>

namespace slang_mcp {
namespace {
void check_thread(int error) {
    if (error != 0) {
        throw std::system_error(error, std::generic_category(), "semantic worker");
    }
}

struct ThreadAttributes {
    pthread_attr_t value{};
    ThreadAttributes() {
        check_thread(pthread_attr_init(&value));
    }
    ~ThreadAttributes() {
        pthread_attr_destroy(&value);
    }
    ThreadAttributes(const ThreadAttributes&) = delete;
    ThreadAttributes& operator=(const ThreadAttributes&) = delete;
};
} // namespace

SemanticExecutor::SemanticExecutor() {
    ThreadAttributes attributes;
    constexpr std::size_t stack_bytes = 16UZ * 1024 * 1024;
    check_thread(pthread_attr_setstacksize(&attributes.value, stack_bytes));
    check_thread(pthread_create(&thread_, &attributes.value, start, this));
}

SemanticExecutor::~SemanticExecutor() {
    {
        const std::lock_guard lock(mutex_);
        stopping_ = true;
    }
    ready_.notify_one();
    pthread_join(thread_, nullptr);
}

Json SemanticExecutor::execute(std::function<Json()> action) {
    std::packaged_task<Json()> task(std::move(action));
    auto result = task.get_future();
    {
        const std::lock_guard lock(mutex_);
        tasks_.push(std::move(task));
    }
    ready_.notify_one();
    return result.get();
}

void* SemanticExecutor::start(void* context) {
    static_cast<SemanticExecutor*>(context)->run();
    return nullptr;
}

void SemanticExecutor::run() {
    for (;;) {
        std::unique_lock lock(mutex_);
        ready_.wait(lock, [this] { return stopping_ || !tasks_.empty(); });
        if (tasks_.empty()) {
            return;
        }
        auto task = std::move(tasks_.front());
        tasks_.pop();
        lock.unlock();
        task();
    }
}
} // namespace slang_mcp
