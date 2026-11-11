#pragma once

#include "hids/audit/plugin_session.hpp"
#include "hids/pilot/transport.hpp"

namespace hids::audit {
struct PluginScope {
    std::string activation, generation, lease;
};

// The channel must already be connected to a verified ingestion peer.
PluginSession make_plugin_session(pilot::Channel& channel, PluginScope scope,
                                  PluginSession::Validate validate, PluginSession::Clock clock = {});
// A best-effort final report. The stream closes even if its ACK is unconfirmed.
bool report_plugin_gap(pilot::Channel&, const PluginScope&, std::string_view code);
}
