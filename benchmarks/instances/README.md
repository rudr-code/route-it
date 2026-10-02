# Benchmark Instances Guide

This directory stores benchmark instances for Route.it. All reported benchmark metrics must originate strictly from actual execution runs on instances stored here.

---

## 1. Where to Get Benchmark Instances

### CVRPLIB X-Instances (Uchoa et al., 2017)
- **Official Portal**: [CVRPLIB Database](http://vrp.galgos.inf.puc-rio.br/index.php/en/)
- **Section**: Go to **Instances** -> **CVRP** -> **Set X (Uchoa et al. 2017)**.
- Download the `.vrp` files directly and place them into this directory (`benchmarks/instances/`).

### Solomon CVRPTW Instances (Solomon, 1987)
- **SINTEF Portal**: [SINTEF Solomon Benchmark](https://www.sintef.no/projectweb/top/vrp/vrptw/solomon-benchmark/)
- **Alternative Mirror**: [Solomon VRPTW Repository](http://web.cba.neu.edu/~msolomon/problems.htm)
- Download the 100-customer `.txt` files directly into this directory (`benchmarks/instances/`).

---

## 2. Recommended Initial Benchmark Instances

To evaluate performance across different problem topologies and constraint regimes, start with these **11 primary instances**:

### A. 5 Small CVRPLIB X-Instances
These are the 5 smallest modern instances from the Uchoa et al. (2017) benchmark set:
1. `X-n101-k25.vrp` (100 customers, 25 vehicles, tight capacity)
2. `X-n106-k14.vrp` (105 customers, 14 vehicles)
3. `X-n110-k9.vrp` (109 customers, 9 vehicles)
4. `X-n115-k10.vrp` (114 customers, 10 vehicles)
5. `X-n120-k6.vrp` (119 customers, 6 vehicles, wide routes)

### B. 6 Solomon CVRPTW Instances
A balanced selection across geographical distribution and scheduling horizons:
1. `C101.txt` — **Clustered** customers, short scheduling horizon, tight time windows.
2. `C201.txt` — **Clustered** customers, long scheduling horizon, larger vehicle capacity.
3. `R101.txt` — **Randomly distributed** customers, short scheduling horizon, tight time windows.
4. `R201.txt` — **Randomly distributed** customers, long scheduling horizon, larger capacity.
5. `RC101.txt` — **Random-Clustered** mixture, short horizon, tight time windows.
6. `RC201.txt` — **Random-Clustered** mixture, long horizon, larger capacity.

---

## 3. Directory Layout
Place the downloaded files directly here:
```
benchmarks/instances/
├── README.md
├── A-n32-k5.vrp       # Standard test fixture (pre-included)
├── X-n101-k25.vrp
├── X-n106-k14.vrp
├── X-n110-k9.vrp
├── X-n115-k10.vrp
├── X-n120-k6.vrp
├── C101.txt
├── C201.txt
├── R101.txt
├── R201.txt
├── RC101.txt
└── RC201.txt
```

---

## 4. Verifying Instances

Run the validation script from the repository root to verify file presence and parsing integrity:
```bash
python benchmarks/check_instances.py
```
This script validates that each instance file is present, parses cleanly without schema errors, and displays parsed customer counts, vehicle counts, and capacities.
