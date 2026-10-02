# Route.it Benchmark Instances Directory

This directory stores benchmark instances for evaluating Route.it's quantum-inspired solver (QPSO) against standard metaheuristics and baseline solvers (Google OR-Tools).

> [!IMPORTANT]
> **Data Integrity Principle**:
> All benchmark results and metrics reported in Route.it documentation and research papers originate strictly from genuine execution runs executed on instances stored in this directory.

---

## 1. Solomon CVRPTW Benchmark Set (1987)

The 100-customer Solomon benchmark is the standard international test suite for Capacitated Vehicle Routing Problems with Time Windows (CVRPTW).

### Required Files
Place the following standard `.txt` files directly into `benchmarks/instances/`:
- **Clustered Customers**:
  - `C101.txt` (short scheduling horizon, tight time windows)
  - `C102.txt`, `C103.txt`, `C104.txt`, `C105.txt`, `C106.txt`, `C107.txt`, `C108.txt`, `C109.txt`
  - `C201.txt` - `C208.txt` (long scheduling horizon, larger vehicle capacity)
- **Randomly Distributed Customers**:
  - `R101.txt` - `R112.txt`
  - `R201.txt` - `R211.txt`
- **Mixed Clustered & Random Customers**:
  - `RC101.txt` - `RC108.txt`
  - `RC201.txt` - `RC208.txt`

### Official Download Sources
You can download the canonical Solomon benchmark files from:
- **SINTEF Applied Mathematics**: https://www.sintef.no/projectweb/top/vrp/vrptw/solomon-benchmark/
- **Solomon Benchmark Repository (Wichmann)**: http://web.cba.neu.edu/~msolomon/problems.htm

### File Format Specification
```
<Instance Name>
VEHICLE
NUMBER     CAPACITY
   25         200

CUSTOMER
CUST NO.  XCOORD.   YCOORD.    DEMAND   READY TIME  DUE DATE   SERVICE TIME
    0        40.0      50.0       0.0          0.0    1236.0            0.0
    1        45.0      68.0      10.0        912.0     967.0           90.0
...
```

---

## 2. CVRPLIB Benchmark Instances (TSPLIB Format)

The CVRPLIB benchmark repository provides classic CVRP instances across various sizes and topologies (Augerat et al. 1995, Christofides & Eilon 1969, Uchoa et al. 2017).

### Suggested Instances
- `A-n32-k5.vrp` (Included as standard reference fixture)
- `A-n45-k6.vrp`
- `B-n31-k5.vrp`
- `P-n16-k8.vrp`

### Official Download Source
- **CVRPLIB Database**: http://vrp.galgos.inf.puc-rio.br/index.php/en/

### File Format Specification
```
NAME : A-n32-k5
COMMENT : (Augerat et al, Min no of trucks: 5, Optimal value: 784)
TYPE : CVRP
DIMENSION : 32
EDGE_WEIGHT_TYPE : EUC_2D
CAPACITY : 100
NODE_COORD_SECTION
 1 82 76
 2 96 44
...
DEMAND_SECTION
 1 0
 2 19
...
DEPOT_SECTION
 1
 -1
EOF
```
