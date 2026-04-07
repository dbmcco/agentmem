#!/usr/bin/env bash
# ABOUTME: Sample facet bootstrap for a personal assistant agent.
# ABOUTME: Edit the values below to match your agent's actual identity and user profile.
#
# This script seeds the identity layer — the stable facts that anchor every context window.
# Run it once when setting up a new agent, and re-run any line when something changes.
#
# Usage:
#   export AGENTMEM_URL=http://localhost:3510
#   export AGENTMEM_TENANT=myagent
#   bash examples/bootstrap_facets.sh
#
# Or pass tenant directly:
#   AGENTMEM_TENANT=aria bash examples/bootstrap_facets.sh

set -euo pipefail

TENANT="${AGENTMEM_TENANT:-myagent}"
URL="${AGENTMEM_URL:-http://localhost:3510}"

ingest_facet() {
  # args: key value layer confidence
  curl -sf -X POST "$URL/ingest/facet" \
    -H "Content-Type: application/json" \
    -d "{\"tenant_id\":\"$TENANT\",\"key\":\"$1\",\"value\":\"$2\",\"layer\":\"$3\",\"confidence\":$4}" \
    > /dev/null
  echo "  set $1 = $2"
}

ingest_triplet() {
  # args: subject predicate object confidence source
  curl -sf -X POST "$URL/ingest/triplet" \
    -H "Content-Type: application/json" \
    -d "{\"tenant_id\":\"$TENANT\",\"subject\":\"$1\",\"predicate\":\"$2\",\"object\":\"$3\",\"confidence\":$4,\"source\":\"$5\"}" \
    > /dev/null
  echo "  triplet: $1 / $2 / $3"
}

echo "==> Bootstrapping agent identity for tenant: $TENANT"
echo ""

# ── PERSONA ──────────────────────────────────────────────────────────────────
# These facets define who the agent is. They appear in every context window and
# shape every response. Set these deliberately — they are the foundation of
# consistent agent behavior.
echo "--> persona.*"

# The agent's name, if it has one. Optional but helps the agent refer to itself
# consistently.
ingest_facet "persona.name" "Aria" "identity" 1.0

# The agent's core function. Keep this a single sentence.
ingest_facet "persona.role" "personal assistant" "identity" 1.0

# Tone shapes how the agent expresses itself — the emotional register of responses.
# Think: how would you describe how this agent sounds to a new user?
ingest_facet "persona.tone" "warm, direct, and unhurried" "identity" 1.0

# Style is the structural preference — formatting, verbosity, register.
ingest_facet "persona.style" "concise; uses bullet points for lists; avoids jargon unless the user uses it first" "identity" 1.0

# How the agent handles uncertainty. This prevents confident hallucination.
ingest_facet "persona.uncertainty_posture" "acknowledges gaps explicitly; asks clarifying questions rather than guessing" "identity" 1.0

# Boundaries the agent maintains consistently.
ingest_facet "persona.boundaries" "does not speculate about private information; redirects off-topic requests gently" "identity" 0.95

echo ""

# ── USER RELATIONSHIP ────────────────────────────────────────────────────────
# These facets capture what the agent knows about its primary user. The more
# accurate these are, the less the agent has to ask. Update them as you learn
# more — confidence reflects how certain you are.
echo "--> relationship.user.*"

# Basic identity
ingest_facet "relationship.user.name" "Alex" "identity" 1.0
ingest_facet "relationship.user.full_name" "Alex Chen" "identity" 1.0
ingest_facet "relationship.user.timezone" "America/Chicago" "identity" 1.0
ingest_facet "relationship.user.preferred_language" "English" "identity" 1.0

# Communication preferences — how the user likes to interact
ingest_facet "relationship.user.communication_style" "direct; prefers brevity; reads bullet points over paragraphs" "identity" 0.9
ingest_facet "relationship.user.response_length_preference" "short by default; detailed only when asked" "identity" 0.85
ingest_facet "relationship.user.preferred_greeting" "none; gets to the point immediately" "identity" 0.8

# Relational state — the current emotional/relational dynamic.
# "positive" | "neutral" | "cautious" | "strained"
# Update this as the relationship evolves — it affects tone calibration.
ingest_facet "relationship.user.affect" "positive" "identity" 0.75

# Trust level — how much the agent should defer to the user's judgment vs. push back.
# "high" means the agent accepts instructions with minimal friction.
# "moderate" means the agent flags concerns but ultimately defers.
ingest_facet "relationship.user.trust_level" "high" "identity" 0.9

# Working style — when and how the user works
ingest_facet "relationship.user.working_hours" "9am-6pm weekdays, occasionally evenings" "identity" 0.8
ingest_facet "relationship.user.work_style" "async-first; deep work blocks in the morning; meetings in the afternoon" "identity" 0.75

echo ""

# ── WORLD CONTEXT ────────────────────────────────────────────────────────────
# Slow-moving facts about the user's context in the world. These change rarely
# but matter for grounding responses (e.g. what "the team" refers to, what
# tools are standard, what the user's role implies).
echo "--> world.*"

ingest_facet "world.user.role" "software engineer" "identity" 0.95
ingest_facet "world.user.seniority" "senior; 8 years experience" "identity" 0.8
ingest_facet "world.org.name" "Meridian Labs" "identity" 1.0
ingest_facet "world.org.size" "~40 people; Series A startup" "identity" 0.9
ingest_facet "world.org.domain" "developer tooling" "identity" 0.95

# Primary tools and platforms the user works with daily.
# This helps the agent give contextually appropriate advice (e.g. suggesting
# GitHub Actions over Jenkins if the user works in a GitHub shop).
ingest_facet "world.tools.primary_language" "Python" "identity" 0.9
ingest_facet "world.tools.vcs" "GitHub" "identity" 1.0
ingest_facet "world.tools.communication" "Slack" "identity" 1.0
ingest_facet "world.tools.task_management" "Linear" "identity" 0.9
ingest_facet "world.tools.editor" "VS Code" "identity" 0.85

echo ""

# ── RUNTIME DEFAULTS ─────────────────────────────────────────────────────────
# Runtime facets are updated during operation — by the agent itself or by your
# runtime layer. These seeds set the initial state. The agent will overwrite
# them as context changes.
echo "--> runtime.*"

# The agent's current operational mode.
# "assistant" | "focus" | "unavailable" — your runtime can add custom modes.
ingest_facet "runtime.mode" "assistant" "runtime" 1.0

# Current task context. Updated by the agent after each significant interaction.
ingest_facet "runtime.current_task" "none" "runtime" 1.0

# Last known active project. Updated when the user mentions switching focus.
ingest_facet "runtime.active_project" "none" "runtime" 0.5

# Session count — incremented by your runtime on each conversation start.
# Useful for detecting early-relationship vs. established-relationship behavior.
ingest_facet "runtime.session_count" "0" "runtime" 1.0

echo ""

# ── KNOWLEDGE GRAPH (TRIPLETS) ───────────────────────────────────────────────
# Triplets encode discrete facts as subject/predicate/object. They complement
# facets — facets describe properties of the agent or user, triplets describe
# relationships between entities in the user's world.
#
# These examples show how to pre-seed known relationships at bootstrap.
# The agent will add more triplets as it learns from conversation.
echo "--> knowledge graph triplets"

# User's relationships and preferences
ingest_triplet "Alex" "works_at" "Meridian Labs" 1.0 "bootstrap"
ingest_triplet "Alex" "prefers" "async communication" 0.9 "bootstrap"
ingest_triplet "Alex" "uses" "Python" 0.9 "bootstrap"
ingest_triplet "Alex" "manages" "backend infrastructure" 0.8 "bootstrap"

# Org structure
ingest_triplet "Meridian Labs" "is_a" "developer tooling startup" 1.0 "bootstrap"
ingest_triplet "Meridian Labs" "uses" "GitHub" 1.0 "bootstrap"
ingest_triplet "Meridian Labs" "uses" "Slack" 1.0 "bootstrap"

echo ""
echo "==> Bootstrap complete."
echo ""
echo "Verify with:"
echo "  curl \"$URL/retrieve/facets?tenant_id=$TENANT&prefix=persona.\" | jq"
echo "  curl \"$URL/retrieve/facets?tenant_id=$TENANT&prefix=relationship.user.\" | jq"
echo "  curl \"$URL/retrieve/graph?tenant_id=$TENANT\" | jq"
