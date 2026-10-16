# Mermaid templates

Copy the closest template, keep the `classDef` lines, then replace the nodes. The
palette and shape rules are in the skill `docs-mermaid-diagrams`.


## 1 Linear pipeline (flowchart LR)

```mermaid
flowchart LR
    SRC[(CSV upload<br/>approx 10 MB)]:::input
    PARSE[Parser<br/>schema v3]:::compute
    VAL{Schema<br/>valid?}:::control
    ENRICH[Enricher<br/>+ geo lookup]:::compute
    DB[(Warehouse<br/>BigQuery)]:::data
    ERR[Quarantine<br/>bucket]:::fail

    SRC -->|raw rows| PARSE
    PARSE --> VAL
    VAL -->|yes| ENRICH
    VAL -->|no| ERR
    ENRICH -->|normalized| DB

    classDef input    fill:#ffe0b2,stroke:#e65100,stroke-width:2px,color:#000
    classDef compute  fill:#ffcdd2,stroke:#b71c1c,stroke-width:2px,color:#000
    classDef control  fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef data     fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef fail     fill:#ef9a9a,stroke:#b71c1c,stroke-width:2px,color:#000
```

## 2 System architecture / functional blocks (block-beta)

```mermaid
block-beta
  columns 3
  block:edge["EDGE"]
    columns 1
    CDN["CDN"]
    LB["Load Balancer"]
    WAF["WAF"]
  end
  block:app["APPLICATION"]
    columns 2
    API["API Gateway"]
    AUTH["Auth Service"]
    WORKER["Worker Pool"]
    SCHED["Scheduler"]
  end
  block:store["DATA"]
    columns 1
    PG[("Postgres")]
    REDIS[("Redis")]
    S3[("Object Store")]
  end

  CDN --> LB
  LB --> API
  API --> AUTH
  API --> WORKER
  SCHED --> WORKER
  WORKER --> PG
  WORKER --> REDIS
  WORKER --> S3

  classDef edge  fill:#cfd8dc,stroke:#37474f,color:#000
  classDef app   fill:#ffcdd2,stroke:#b71c1c,color:#000
  classDef store fill:#bbdefb,stroke:#0d47a1,color:#000
  class edge edge
  class app app
  class store store
```

## 3 Decision tree / troubleshooting (flowchart TD)

```mermaid
flowchart TD
    START([Symptom:<br/>Deploy fails]):::action
    Q1{CI build<br/>green?}:::control
    F1[Fix failing<br/>tests or lints]:::fail
    Q2{Image pushed<br/>to registry?}:::control
    F2[Check registry<br/>credentials]:::fail
    Q3{Pod becomes<br/>Ready?}:::control
    F3[Check resource<br/>limits + secrets]:::fail
    Q4{Health endpoint<br/>returns 200?}:::control
    F4[Inspect logs<br/>and DB connectivity]:::fail
    OK([Service healthy<br/>deploy complete]):::ok

    START --> Q1
    Q1 -->|NO| F1
    Q1 -->|YES| Q2
    Q2 -->|NO| F2
    Q2 -->|YES| Q3
    Q3 -->|NO| F3
    Q3 -->|YES| Q4
    Q4 -->|NO| F4
    Q4 -->|YES| OK

    classDef action  fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000
    classDef control fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef fail    fill:#ef9a9a,stroke:#b71c1c,stroke-width:2px,color:#000
    classDef ok      fill:#a5d6a7,stroke:#1b5e20,stroke-width:2px,color:#000
```

## 4 Sequence diagram (interaction across actors)

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant FE as Frontend
    participant API as API Gateway
    participant DB as Postgres
    participant Q as Job Queue

    U->>FE: Submit form
    FE->>API: POST /orders
    API->>DB: INSERT order (pending)
    DB-->>API: order_id
    API->>Q: enqueue("process_order", id)
    API-->>FE: 202 Accepted
    FE-->>U: "We're processing it"
    Note over Q,DB: Worker picks the job<br/>and updates the row asynchronously
```

## 5 State machine (stateDiagram-v2)

```mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Review: submit
    Review --> Draft: request_changes
    Review --> Approved: approve
    Approved --> Published: publish
    Published --> Archived: archive
    Archived --> [*]

    note right of Review
      Two reviewers required
      before approval.
    end note
```

## 6 Entity-Relationship (erDiagram)

```mermaid
erDiagram
    USER ||--o{ ORDER : places
    ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : "is part of"
    USER {
      uuid   id PK
      string email
      string name
    }
    ORDER {
      uuid   id PK
      uuid   user_id FK
      date   created_at
      string status
    }
    ORDER_ITEM {
      uuid   id PK
      uuid   order_id FK
      uuid   product_id FK
      int    quantity
      money  unit_price
    }
    PRODUCT {
      uuid   id PK
      string sku
      string name
      money  price
    }
```

## 7 Gantt / timeline

```mermaid
gantt
    title Release plan
    dateFormat  YYYY-MM-DD
    section Backend
    Design API           :done,    des1, 2026-05-01, 2026-05-07
    Implement endpoints  :active,  imp1, 2026-05-08, 10d
    Load test            :         lt1,  after imp1, 5d
    section Frontend
    Wireframes           :done,    wf1,  2026-05-01, 2026-05-05
    UI implementation    :active,  ui1,  2026-05-06, 12d
    section Release
    Beta cut             :milestone, m1,  2026-05-25, 0d
    GA                   :milestone, m2,  2026-06-01, 0d
```

## 8 Physical / dashboard layout (block-beta positional)

```mermaid
block-beta
  columns 4
  HEADER["HEADER - Title - Filters - User menu"]:4
  KPI1["KPI - Revenue"]:1 KPI2["KPI - Active users"]:1 KPI3["KPI - Conversion"]:1 KPI4["KPI - Latency p95"]:1
  CHART1["Time-series<br/>revenue"]:2 CHART2["Funnel<br/>signup to paid"]:2
  TABLE["Recent transactions<br/>paginated"]:3 SIDE["Alerts<br/>panel"]:1
  FOOTER["FOOTER - Legal - Status - Version"]:4

  classDef header fill:#cfd8dc,stroke:#37474f,color:#000
  classDef kpi    fill:#ffcdd2,stroke:#b71c1c,color:#000
  classDef chart  fill:#bbdefb,stroke:#0d47a1,color:#000
  classDef side   fill:#fff59d,stroke:#f57f17,color:#000
  class HEADER,FOOTER header
  class KPI1,KPI2,KPI3,KPI4 kpi
  class CHART1,CHART2,TABLE chart
  class SIDE side
```

