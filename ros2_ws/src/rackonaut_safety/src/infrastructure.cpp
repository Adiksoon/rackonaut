#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <deque>
#include <map>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#include <ignition/msgs/boolean.pb.h>
#include <ignition/msgs/empty.pb.h>
#include <ignition/msgs/pose.pb.h>
#include <ignition/msgs/scene.pb.h>
#include <ignition/msgs/visual.pb.h>
#include <ignition/transport/Node.hh>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>

using namespace std::chrono_literals;

namespace {
using Point = std::array<double, 2>;
using Colour = std::array<float, 3>;
using Phases = std::map<std::string, std::string>;

const std::map<std::string, Point> targets{
  {"outside", {3.68, 3.90}}, {"A", {6.45, 1.25}}, {"B", {6.45, -6.60}}, {"T", {2.10, -2.0}}};
const std::map<std::string, std::string> towers{
  {"safety_a_west", "A"}, {"safety_a_east", "A"}, {"safety_b_west", "B"},
  {"safety_b_east", "B"}, {"safety_t_pad", "T"}};
const std::map<std::string, Colour> lamps{
  {"red", {1.f, .025f, .015f}}, {"yellow", {1.f, .64f, .012f}}, {"green", {.025f, 1.f, .12f}}};
const Colour dark{.065f, .076f, .085f};
const Colour black{0.f, 0.f, 0.f};
const std::string world = "/world/rackonaut";
const Point forklift_park{1.95, 7.9};
const Point pallet_park{2.0, 9.8};

void colour(ignition::msgs::Color *value, const Colour &rgb) {
  value->set_r(rgb[0]);
  value->set_g(rgb[1]);
  value->set_b(rgb[2]);
  value->set_a(1.f);
}
}

class Infrastructure : public rclcpp::Node {
 public:
  Infrastructure() : Node("rackonaut_safety_infrastructure"), worker_(targets.at("outside")) {
    phases_ = {{"A", "FAULT"}, {"B", "FAULT"}, {"T", "FAULT"}};
    if (declare_parameter("aerial", false)) {
      active_towers_.emplace("safety_d_tech", "D");
      phases_.emplace("D", "FAULT");
      for (const auto &zone : {"A", "B"}) {
        const auto point = declare_parameter(std::string("descent_") + zone, std::vector<double>{});
        if (point.size() == 2)
          worker_targets_.emplace(std::string("D") + zone, Point{point[0], point[1]});
      }
    }
    ack_ = create_publisher<std_msgs::msg::String>("/rackonaut/safety/signals_applied", 5);
    control_ = create_subscription<std_msgs::msg::String>(
        "/rackonaut/safety/signals", 5, [this](const std_msgs::msg::String &message) {
          std::istringstream input(message.data);
          std::string pair;
          Phases next;
          while (input >> pair) {
            auto separator = pair.find('=');
            if (separator != std::string::npos)
              next.emplace(pair.substr(0, separator), pair.substr(separator + 1));
          }
          if (next.size() == phases_.size() && std::all_of(phases_.begin(), phases_.end(),
              [&next](const auto &entry) { return next.count(entry.first); })) {
            phases_ = std::move(next);
            command_at_ = std::chrono::steady_clock::now();
          }
        });
    worker_control_ = create_subscription<std_msgs::msg::String>(
        "/rackonaut/safety/simulation/worker_target", 5,
        [this](const std_msgs::msg::String &message) { select_worker_target(message.data); });
    laser_props_ = declare_parameter("laser_props", false);
    for (const auto &key : declare_parameter("avoidance_props", std::vector<std::string>{})) {
      const auto points = declare_parameter("prop_" + key, std::vector<double>{});
      if (points.size() == 6) {
        props_.emplace(key, Prop{{points[0], points[1], points[2]}, {points[3], points[4], points[5]}});
      }
    }
    if (laser_props_ || !props_.empty()) {
      obstacles_ = create_subscription<std_msgs::msg::String>(
          "/rackonaut/safety/simulation/obstacle_target", 5,
          [this](const std_msgs::msg::String &message) { select_obstacles(message.data); });
    }
    if (declare_parameter("energy_dock", false)) {
      dock_control_ = create_subscription<std_msgs::msg::String>(
          "/rackonaut/energy/dock_light", 5, [this](const std_msgs::msg::String &message) {
            dock_phase_ = message.data;
            dock_at_ = std::chrono::steady_clock::now();
          });
      dock_timer_ = create_wall_timer(450ms, [this] { update_dock(); });
    }
    lights_timer_ = create_wall_timer(100ms, [this] { update_lamps(); });
    movement_timer_ = create_wall_timer(65ms, [this] {
      step_model("safety_worker", worker_, queue_, .101);
      step_model("safety_forklift", forklift_, forklift_queue_, .14);
    });
  }

 private:
  using Point3 = std::array<double, 3>;
  struct Prop { Point3 park; Point3 location; };

  void update_dock() {
    if (dock_lenses_.size() != lamps.size()) {
      ignition::msgs::Empty request;
      ignition::msgs::Scene scene;
      bool ok = false;
      if (!transport_.Request(world + "/scene/info", request, 150, scene, ok) || !ok)
        return;
      for (const auto &model : scene.model()) {
        if (model.name() != "rackonaut_dock")
          continue;
        for (const auto &link : model.link())
          for (const auto &part : link.visual())
            if (lamps.count(part.name()))
              dock_lenses_[part.name()] = part.id();
      }
    }
    auto phase = std::chrono::steady_clock::now() - dock_at_ > 900ms ? "FAULT" : dock_phase_;
    const std::string active = phase == "FAULT" ? "red" :
        phase == "CHARGING" || phase == "APPROACHING" || phase == "DOCKED" ? "yellow" : "green";
    for (const auto &[lamp, id] : dock_lenses_) {
      bool on = lamp == active;
      if ((!applied_.count(id) || applied_.at(id) != on) && set_lens(id, lamp, on))
        applied_[id] = on;
    }
  }

  bool discover_lamps() {
    ignition::msgs::Empty request;
    ignition::msgs::Scene scene;
    bool ok = false;
    if (!transport_.Request(world + "/scene/info", request, 150, scene, ok) || !ok)
      return false;
    for (const auto &model : scene.model()) {
      if (!active_towers_.count(model.name()))
        continue;
      for (const auto &link : model.link()) {
        for (const auto &part : link.visual()) {
          if (lamps.count(part.name()))
            lenses_[{model.name(), part.name()}] = part.id();
        }
      }
    }
    return lenses_.size() == active_towers_.size() * lamps.size();
  }

  bool set_lens(uint32_t id, const std::string &lamp, bool on) {
    ignition::msgs::Visual request;
    request.set_id(id);
    auto *material = request.mutable_material();
    colour(material->mutable_ambient(), on ? lamps.at(lamp) : dark);
    colour(material->mutable_diffuse(), on ? lamps.at(lamp) : dark);
    colour(material->mutable_emissive(), on ? lamps.at(lamp) : black);
    ignition::msgs::Boolean reply;
    bool result = false;
    return transport_.Request(world + "/visual_config", request, 120, reply, result)
        && result && reply.data();
  }

  void update_lamps() {
    auto now = std::chrono::steady_clock::now();
    if (lenses_.size() != active_towers_.size() * lamps.size() && !discover_lamps())
      return;
    if (now - command_at_ > 900ms)
      for (auto &entry : phases_)
        entry.second = "FAULT";
    const auto clock = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch());
    const bool flash = clock.count() % 800 < 400;
    for (const auto &[key, id] : lenses_) {
      const auto &[tower, lamp] = key;
      const auto &phase = phases_.at(active_towers_.at(tower));
      bool on = (phase == "OPEN" && lamp == "green")
          || (phase == "PREPARING" && lamp == "yellow")
          || (phase == "RESERVED" && lamp == "red")
          || (phase == "INTRUSION" && lamp == "red" && flash)
          || (phase == "FAULT" && (lamp == "red" || lamp == "yellow"));
      auto previous = applied_.find(id);
      if (previous != applied_.end() && previous->second == on)
        continue;
      if (!set_lens(id, lamp, on))
        return;
      applied_[id] = on;
    }
    std_msgs::msg::String message;
    for (const auto &[zone, phase] : phases_)
      message.data += (message.data.empty() ? "" : " ") + zone + "=" + phase;
    ack_->publish(message);
  }

  void select_worker_target(const std::string &choice) {
    const auto found = worker_targets_.find(choice);
    if (found == worker_targets_.end())
      return;
    const auto &point = found->second;
    // Keep the figure in front of the rack faces while it changes aisles.
    queue_ = {{3.68, worker_[1]}, {3.68, point[1]}, point};
  }

  void select_obstacles(const std::string &choice) {
    if (choice == "clear_flight" || props_.count(choice)) {
      if (!active_prop_.empty()) {
        if (!set_pose_3d("avoidance_" + active_prop_, props_.at(active_prop_).park, 0.))
          return;
        active_prop_.clear();
      }
      const auto found = props_.find(choice);
      if (found != props_.end() && set_pose_3d("avoidance_" + choice, found->second.location, 0.))
        active_prop_ = choice;
      return;
    }
    if (!laser_props_)
      return;
    if (choice == "forklift_a") {
      forklift_queue_ = {{2.55, forklift_[1]}, {2.55, .87}, {7.15, .87}};
    } else if (choice == "pallet_b") {
      set_pose("safety_pallet", {6.65, -6.10}, 0.);
    } else if (choice == "clear") {
      forklift_queue_ = {{2.55, forklift_[1]}, {2.55, forklift_park[1]}, forklift_park};
      set_pose("safety_pallet", pallet_park, 0.);
    }
  }

  void step_model(const std::string &model, Point &current, std::deque<Point> &queue, double metres) {
    if (queue.empty())
      return;
    auto [x, y] = queue.front();
    const double dx = x - current[0], dy = y - current[1];
    const double distance = std::hypot(dx, dy);
    if (distance < 1e-6) {
      queue.pop_front();
      return;
    }
    const double step = std::min(1., metres / distance);
    Point next{current[0] + dx * step, current[1] + dy * step};
    if (set_pose(model, next, std::atan2(dy, dx))) {
      current = next;
      if (step == 1.)
        queue.pop_front();
    }
  }

  bool set_pose(const std::string &model, const Point &point, double yaw) {
    return set_pose_3d(model, {point[0], point[1], 0.}, yaw);
  }

  bool set_pose_3d(const std::string &model, const Point3 &point, double yaw) {
    ignition::msgs::Pose request;
    request.set_name(model);
    request.mutable_position()->set_x(point[0]);
    request.mutable_position()->set_y(point[1]);
    request.mutable_position()->set_z(point[2]);
    request.mutable_orientation()->set_z(std::sin(yaw * .5));
    request.mutable_orientation()->set_w(std::cos(yaw * .5));
    ignition::msgs::Boolean reply;
    bool result = false;
    return transport_.Request(world + "/set_pose", request, 100, reply, result) && result && reply.data();
  }

  ignition::transport::Node transport_;
  bool laser_props_;
  std::map<std::string, Prop> props_;
  std::string active_prop_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr ack_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr control_, worker_control_, obstacles_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr dock_control_;
  rclcpp::TimerBase::SharedPtr lights_timer_, movement_timer_;
  rclcpp::TimerBase::SharedPtr dock_timer_;
  Phases phases_;
  std::map<std::string, std::string> active_towers_ = towers;
  std::map<std::string, Point> worker_targets_ = targets;
  std::chrono::steady_clock::time_point command_at_;
  std::chrono::steady_clock::time_point dock_at_;
  std::string dock_phase_ = "FAULT";
  std::map<std::string, uint32_t> dock_lenses_;
  std::map<std::pair<std::string, std::string>, uint32_t> lenses_;
  std::map<uint32_t, bool> applied_;
  Point worker_;
  Point forklift_ = forklift_park;
  std::deque<Point> queue_, forklift_queue_;
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<Infrastructure>());
  rclcpp::shutdown();
}
