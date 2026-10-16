# ZION Knowledge Authority Manifest

This manifest is the machine-readable authority boundary for local retrieval.
Every Markdown source loaded as knowledge must appear here. Missing, malformed,
historical, superseded, excluded, internal, or secret sources fail closed before
model context is built.

```json
{
  "schema_version": 1,
  "sources": [
    {
      "file": "community.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "2026-09-24",
      "source_identity": "zion-community-policy",
      "allowed_agents": ["zion", "eir"]
    },
    {
      "file": "product.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "2026-09-24",
      "source_identity": "zswap-public-product-policy",
      "allowed_agents": ["zion", "mimir", "eir", "freyr"]
    },
    {
      "file": "z-swap-plans.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "2026-09-24",
      "source_identity": "zswap-public-plan-matrix",
      "allowed_agents": ["zion", "mimir", "eir", "freyr"]
    },
    {
      "file": "z-swap.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "25fc4b0fa55db72472c7ae00af42596209d7c362",
      "source_identity": "zswap-curated-public-snapshot",
      "allowed_agents": ["zion", "mimir", "eir", "freyr"]
    },
    {
      "file": "zion-faq.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "2026-09-24",
      "source_identity": "zion-community-faq",
      "allowed_agents": ["zion", "eir"]
    },
    {
      "file": "zswap-features.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "25fc4b0fa55db72472c7ae00af42596209d7c362",
      "source_identity": "zswap-curated-feature-snapshot",
      "allowed_agents": ["zion", "mimir", "eir", "freyr"]
    },
    {
      "file": "zswap-safety-boundary.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "25fc4b0fa55db72472c7ae00af42596209d7c362",
      "source_identity": "zswap-public-disclosure-policy",
      "allowed_agents": ["zion", "mimir", "eir", "freyr"]
    },
    {
      "file": "zswap-status.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "25fc4b0fa55db72472c7ae00af42596209d7c362",
      "source_identity": "zswap-curated-status-snapshot",
      "allowed_agents": ["zion", "mimir", "eir", "freyr"]
    }
  ]
}
```
