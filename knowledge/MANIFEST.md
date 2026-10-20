# ZION Knowledge Authority Manifest

This manifest is the machine-readable authority boundary for local retrieval.
Every Markdown source loaded as knowledge must appear here. Missing, malformed,
historical, superseded, excluded, internal, or secret sources fail closed before
model context is built.

```json
{
  "schema_version": 2,
  "sources": [
    {
      "file": "community.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "2026-09-24",
      "source_identity": "zion-community-policy",
      "allowed_agents": [
        "zion",
        "eir"
      ],
      "id": "zion-community-policy",
      "title": "Z-SWAP Community",
      "source_type": "curated_local_projection",
      "snapshot_date": "2026-09-24",
      "authority": "zion-community-policy",
      "supersedes": [],
      "superseded_by": null,
      "freshness": "snapshot_only",
      "valid_until": null,
      "notes": "Versioned approved projection; snapshot is not proof of current deployed behavior. Source changes require explicit reconciliation."
    },
    {
      "file": "product.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "2026-09-24",
      "source_identity": "zswap-public-product-policy",
      "allowed_agents": [
        "zion",
        "mimir",
        "eir",
        "freyr"
      ],
      "id": "zswap-public-product-policy",
      "title": "Product Knowledge Policy",
      "source_type": "curated_local_projection",
      "snapshot_date": "2026-09-24",
      "authority": "zswap-public-product-policy",
      "supersedes": [],
      "superseded_by": null,
      "freshness": "snapshot_only",
      "valid_until": null,
      "notes": "Versioned approved projection; snapshot is not proof of current deployed behavior. Source changes require explicit reconciliation."
    },
    {
      "file": "z-swap-plans.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "986ae759c1c76fe23967a8e61489d986b2bb9a51@2026-10-18",
      "source_identity": "zswap-public-plan-matrix",
      "allowed_agents": [
        "zion",
        "mimir",
        "eir",
        "freyr"
      ],
      "id": "zswap-public-plan-matrix",
      "title": "Matriz pública atual dos planos da Z-SWAP",
      "source_type": "curated_local_projection",
      "snapshot_date": "2026-10-18",
      "authority": "zswap-public-plan-matrix",
      "supersedes": [],
      "superseded_by": null,
      "freshness": "snapshot_only",
      "valid_until": null,
      "notes": "Versioned approved projection; snapshot is not proof of current deployed behavior. Source changes require explicit reconciliation."
    },
    {
      "file": "z-swap.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "166fd5be9c28fb2ffaaffd9413bf61c40f492698@2026-10-16",
      "source_identity": "zswap-curated-public-snapshot",
      "allowed_agents": [
        "zion",
        "mimir",
        "eir",
        "freyr"
      ],
      "id": "zswap-curated-public-snapshot",
      "title": "O que é a Z-SWAP?",
      "source_type": "curated_local_projection",
      "snapshot_date": "2026-10-16",
      "authority": "zswap-curated-public-snapshot",
      "supersedes": [],
      "superseded_by": null,
      "freshness": "snapshot_only",
      "valid_until": null,
      "notes": "Versioned approved projection; snapshot is not proof of current deployed behavior. Source changes require explicit reconciliation."
    },
    {
      "file": "zswap-apn.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "f11814ff833a86f974b4ddd0fc14ad2e9372afe52ffd4dff206315de3a8b5c4d@2026-10-16",
      "source_identity": "zswap-apn-21-page-reconciled",
      "allowed_agents": [
        "zion",
        "mimir",
        "eir",
        "freyr"
      ],
      "id": "zswap-apn-21-page-reconciled",
      "title": "Z-SWAP — Posicionamento institucional público",
      "source_type": "curated_local_projection",
      "snapshot_date": "2026-10-16",
      "authority": "zswap-apn-21-page-reconciled",
      "supersedes": [],
      "superseded_by": null,
      "freshness": "snapshot_only",
      "valid_until": null,
      "notes": "Versioned approved projection; snapshot is not proof of current deployed behavior. Source changes require explicit reconciliation."
    },
    {
      "file": "zion-faq.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "2026-09-24",
      "source_identity": "zion-community-faq",
      "allowed_agents": [
        "zion",
        "eir"
      ],
      "id": "zion-community-faq",
      "title": "ZION — Community FAQ",
      "source_type": "curated_local_projection",
      "snapshot_date": "2026-09-24",
      "authority": "zion-community-faq",
      "supersedes": [],
      "superseded_by": null,
      "freshness": "snapshot_only",
      "valid_until": null,
      "notes": "Versioned approved projection; snapshot is not proof of current deployed behavior. Source changes require explicit reconciliation."
    },
    {
      "file": "zswap-features.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "166fd5be9c28fb2ffaaffd9413bf61c40f492698@2026-10-16",
      "source_identity": "zswap-curated-feature-snapshot",
      "allowed_agents": [
        "zion",
        "mimir",
        "eir",
        "freyr"
      ],
      "id": "zswap-curated-feature-snapshot",
      "title": "Z-SWAP — Guia Público de Recursos",
      "source_type": "curated_local_projection",
      "snapshot_date": "2026-10-16",
      "authority": "zswap-curated-feature-snapshot",
      "supersedes": [],
      "superseded_by": null,
      "freshness": "snapshot_only",
      "valid_until": null,
      "notes": "Versioned approved projection; snapshot is not proof of current deployed behavior. Source changes require explicit reconciliation."
    },
    {
      "file": "zswap-safety-boundary.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "166fd5be9c28fb2ffaaffd9413bf61c40f492698@2026-10-16",
      "source_identity": "zswap-public-disclosure-policy",
      "allowed_agents": [
        "zion",
        "mimir",
        "eir",
        "freyr"
      ],
      "id": "zswap-public-disclosure-policy",
      "title": "Z-SWAP — Limite Público de Segurança e Confidencialidade",
      "source_type": "curated_local_projection",
      "snapshot_date": "2026-10-16",
      "authority": "zswap-public-disclosure-policy",
      "supersedes": [],
      "superseded_by": null,
      "freshness": "snapshot_only",
      "valid_until": null,
      "notes": "Versioned approved projection; snapshot is not proof of current deployed behavior. Source changes require explicit reconciliation."
    },
    {
      "file": "zswap-status.md",
      "classification": "PUBLIC",
      "status": "CURRENT",
      "version": "166fd5be9c28fb2ffaaffd9413bf61c40f492698@2026-10-16",
      "source_identity": "zswap-curated-status-snapshot",
      "allowed_agents": [
        "zion",
        "mimir",
        "eir",
        "freyr"
      ],
      "id": "zswap-curated-status-snapshot",
      "title": "Z-SWAP — Estado Público do Produto",
      "source_type": "curated_local_projection",
      "snapshot_date": "2026-10-16",
      "authority": "zswap-curated-status-snapshot",
      "supersedes": [],
      "superseded_by": null,
      "freshness": "snapshot_only",
      "valid_until": null,
      "notes": "Versioned approved projection; snapshot is not proof of current deployed behavior. Source changes require explicit reconciliation."
    },
    {
      "file": "zswap-technical-public.md",
      "classification": "CONTROLLED",
      "status": "CURRENT",
      "version": "drive-technical-paper-plan-2026-10-14@166fd5be",
      "source_identity": "zswap-technical-paper-public-projection",
      "allowed_agents": [
        "mimir"
      ],
      "id": "zswap-technical-paper-public-projection",
      "title": "Arquitetura pública da Z-SWAP",
      "source_type": "curated_local_projection",
      "snapshot_date": "2026-10-14",
      "authority": "zswap-technical-paper-public-projection",
      "supersedes": [],
      "superseded_by": null,
      "freshness": "snapshot_only",
      "valid_until": null,
      "notes": "Versioned approved projection; snapshot is not proof of current deployed behavior. Source changes require explicit reconciliation."
    }
  ]
}
```

Schema 2 records provenance and reciprocal supersession links. Conflicting or
cyclic links reject the manifest; DRAFT/UNVERIFIED never enter retrieval.
`expires` requires an ISO UTC-date `valid_until` and is checked at retrieval,
not only reload. `snapshot_only` is explicitly not a live freshness guarantee.
