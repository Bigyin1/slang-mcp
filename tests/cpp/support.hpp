#pragma once

#include "semantic_service.hpp"

#include <atomic>
#include <chrono>
#include <filesystem>
#include <fstream>

namespace slang_mcp::test {
class Project {
  public:
    Project() : root_(std::filesystem::temp_directory_path() / unique_name()) {
        std::filesystem::create_directory(root_);
    }
    ~Project() {
        std::error_code error;
        std::filesystem::remove_all(root_, error);
    }
    Project(const Project&) = delete;
    Project& operator=(const Project&) = delete;
    Project(Project&&) = delete;
    Project& operator=(Project&&) = delete;

    void write(const std::string& name, std::string_view contents) const {
        std::ofstream output(root_ / name);
        output << contents;
        if (!output) {
            throw std::runtime_error("cannot write test fixture");
        }
    }

    [[nodiscard]] std::filesystem::path path(const std::string& name) const {
        return root_ / name;
    }

    [[nodiscard]] Json arguments(const std::vector<std::string>& files = {"design.sv"}) const {
        std::vector<std::string> sources;
        for (const auto& file : files) {
            sources.push_back(path(file).string());
        }
        return {{"source_files", sources}, {"top_module", "top"}};
    }

  private:
    std::filesystem::path root_;

    static std::string unique_name() {
        static std::atomic<unsigned> sequence = 0;
        return "slang-mcp-test-" +
               std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + "-" +
               std::to_string(sequence++);
    }
};

inline constexpr std::string_view hierarchy_rtl = R"sv(
module leaf #(parameter int WIDTH = 8)(input logic [WIDTH-1:0] i, output logic [WIDTH-1:0] o);
  assign o = i;
endmodule
module branch(input logic [31:0] data);
  leaf #(.WIDTH(32)) u_c(.i(data), .o());
endmodule
module top;
  logic [31:0] data;
  leaf #(.WIDTH(32)) u_a(.i(data), .o());
  branch u_b(.data(data));
  for (genvar i=0; i<2; i++) begin: generated
    leaf #(.WIDTH(32)) u_leaf(.i(data), .o());
  end
  if (0) begin: inactive
    leaf ghost(.i(data), .o());
  end
endmodule
)sv";
} // namespace slang_mcp::test
