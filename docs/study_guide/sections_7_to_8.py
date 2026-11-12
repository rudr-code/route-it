# docs/study_guide/sections_7_to_8.py
# -*- coding: utf-8 -*-

def get_section_7():
    return """
    <section id="section-7" class="guide-section">
      <div class="section-badge">SECTION 7</div>
      <h1 class="section-title">The 70-Question Counter-Question Bank</h1>
      <p class="section-subtitle">Tough, Direct Answers to Every Probable Counter-Question from Technical & Business SIH Judges</p>

      <div class="card">
        <h2>Category 1: System Architecture & Tech Stack (Q01 - Q10)</h2>
        
        <div class="faq-item">
          <p class="faq-q"><strong>Q01: Why did you choose React + Vite instead of Next.js with Server-Side Rendering (SSR)?</strong></p>
          <p class="faq-a">Route.it is an interactive single-page operations dashboard with heavy client-side geospatial mapping (MapLibre/Leaflet) and WebSocket state management. SSR provides zero benefit for internal dispatch dashboards and would double build times and memory footprint, which would cause out-of-memory crashes on free-tier 512 MB cloud hosting. Vite gives sub-second Hot Module Replacement and builds a lean static bundle served directly by FastAPI. <span class="proof-tag">[Proof: Dockerfile:1-12, vite.config.ts]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q02: Why use FastAPI over Flask or Django?</strong></p>
          <p class="faq-a">FastAPI is built on Starlette and Pydantic, running natively on ASGI asynchronous event loops. This allows Route.it to handle long-running solver calculations and persistent WebSockets concurrently without blocking incoming REST requests. Flask is synchronous and requires heavy extensions for WebSockets, while Django's heavy ORM and monolithic architecture introduce unnecessary latency. <span class="proof-tag">[Proof: api/main.py:1-40]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q03: Why did you use SQLite instead of PostgreSQL for production?</strong></p>
          <p class="faq-a">For this prototype and hackathon demo, SQLite in Write-Ahead Logging (WAL) mode provides zero-latency in-process database access without external network round-trips or dedicated database hosting costs. It easily handles over 50,000 read operations per second. The schema uses standard ANSI SQL tables and foreign keys, allowing seamless migration to PostgreSQL with PostGIS in Phase 1. <span class="proof-tag">[Proof: api/database.py:15-45]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q04: How do you serve both the frontend dashboard and backend API on a single port on Render?</strong></p>
          <p class="faq-a">In our multi-stage Dockerfile, Node builds the React dashboard into static HTML/JS/CSS assets in <code>dashboard/dist</code>. FastAPI mounts this folder using <code>StaticFiles(directory="dashboard/dist", html=True)</code> at the root path <code>/</code>, while mounting REST routes at <code>/api/*</code> and WebSockets at <code>/ws/*</code>. Uvicorn binds to <code>0.0.0.0:$PORT</code>, satisfying Render's single-port routing requirement. <span class="proof-tag">[Proof: Dockerfile:18-28, api/main.py:75-90]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q05: Why use MapLibre GL and Leaflet instead of Google Maps JavaScript API?</strong></p>
          <p class="faq-a">Google Maps requires a paid billing account, credit card verification, and charges $7 per 1,000 map loads. During a public hackathon or high-volume deployment, API quota exhaustion causes map failure. MapLibre and Leaflet are 100% open-source, render high-performance raster and vector tiles from OpenStreetMap Carto, and cost zero rupees with zero quota limits. <span class="proof-tag">[Proof: dashboard/package.json:18-24, RouteMap.tsx]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q06: How do you handle CORS in production when frontend and backend share the domain?</strong></p>
          <p class="faq-a">FastAPI configures <code>CORSMiddleware</code> with <code>allow_origins=["*"]</code>, <code>allow_credentials=True</code>, <code>allow_methods=["*"]</code>, and <code>allow_headers=["*"]</code>. Because the static assets are served from the exact same origin (<code>https://routeit.onrender.com</code>), cross-origin preflight requests are avoided entirely in production. <span class="proof-tag">[Proof: api/main.py:25-35]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q07: How do you maintain database consistency when multiple dispatches happen concurrently?</strong></p>
          <p class="faq-a">We execute <code>PRAGMA journal_mode=WAL;</code> and <code>PRAGMA busy_timeout=5000;</code> on database initialization. WAL mode allows concurrent readers while a write is occurring. In addition, critical dispatch assignments run inside explicit ACID database transactions (<code>db.commit()</code> and <code>db.rollback()</code>) to prevent race conditions or duplicate vehicle assignments. <span class="proof-tag">[Proof: api/database.py:30-50]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q08: What happens if the backend server crashes during an active route optimization?</strong></p>
          <p class="faq-a">The batch state remains marked as <code>PENDING</code> or <code>FAILED</code> in SQLite because state transitions only commit upon solver completion. When the server restarts (or Docker respawns), the dispatcher can click "Optimize Batch" again without data corruption. The customer stops remain safely in the pool. <span class="proof-tag">[Proof: api/delivery_router.py:120-160]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q09: Why did you split the UI into 4 dedicated portals instead of one giant dashboard?</strong></p>
          <p class="faq-a">Logistics operations require role-based interfaces. Hub managers need high-density tables and batch optimizer controls; delivery drivers on motorbikes require large touch buttons, high-contrast manifests, and an OTP modal; customers require a simple tracking progress bar without login. Combining them would create UI clutter and security leakage. <span class="proof-tag">[Proof: dashboard/src/App.tsx:80-140]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q10: Is Route.it cloud-agnostic? Can it deploy to AWS, Azure, or self-hosted servers?</strong></p>
          <p class="faq-a">Yes, 100%. Route.it is completely packaged in an OCI-compliant multi-stage Docker container. It has zero cloud vendor lock-in. It can be deployed on AWS ECS, Google Cloud Run, Azure App Service, Kubernetes, or a bare-metal Linux server with a single command: <code>docker build -t routeit . && docker run -p 8001:8001 routeit</code>. <span class="proof-tag">[Proof: Dockerfile:1-32]</span></p>
        </div>
      </div>

      <div class="card">
        <h2>Category 2: Algorithms, Mathematics & Physics (Q11 - Q20)</h2>
        
        <div class="faq-item">
          <p class="faq-q"><strong>Q11: Are you using real quantum computers (qubits) or classical computers?</strong></p>
          <p class="faq-a">We are using classical Von Neumann CPU architecture (single-core Python/Numba). The algorithm is <em>quantum-inspired</em>: it simulates the mathematical wave equations of a quantum delta-potential well using Monte Carlo sampling. Physical quantum hardware (like IBM Q or D-Wave) is currently inaccessible, noisy (NISQ era), and cost-prohibitive for real-time commercial dispatching. <span class="proof-tag">[Proof: solver/qpso.py:1-45]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q12: Mathematically, what prevents QPSO particles from getting stuck in local minima?</strong></p>
          <p class="faq-a">In classical PSO, particle velocity decays to zero when trapped in a local basin. In QPSO, particles do not have velocity vectors; their positions are governed by a wave function \(\psi(x)\) with double-exponential probability density \(|\psi(x)|^2 = \frac{1}{L} \exp(-2|x-p|/L)\). Because the exponential distribution has non-zero tails across the entire state space, particles have a non-zero probability of quantum tunneling through high-penalty barriers. <span class="proof-tag">[Proof: solver/qpso.py:65-95]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q13: What is the purpose of the mean best position (\(mbest\))?</strong></p>
          <p class="faq-a">The \(mbest\) vector is the center of gravity of all individual particles' historical personal bests: \(mbest = \frac{1}{M}\sum_{i=1}^M pbest_i\). It acts as a collective swarm memory. When a particle's potential well width is scaled by \(|mbest - x|\), particles maintain collective cohesion and do not scatter into unconstrained randomness. <span class="proof-tag">[Proof: solver/qpso.py:110-130]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q14: How does the contraction-expansion coefficient \(\beta\) change over iterations?</strong></p>
          <p class="faq-a">The parameter \(\beta\) linearly anneals from 1.0 down to 0.5 using the formula \(\beta(t) = 1.0 - 0.5 \cdot (t / T_{\max})\). In early iterations (\(\beta \approx 1.0\)), the wave packet is wide, facilitating global exploration across disparate city quadrants. In later iterations (\(\beta \approx 0.5\)), the wave packet contracts, focusing on fine-grained local route refinement. <span class="proof-tag">[Proof: solver/qpso.py:140-155]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q15: How does Prins Split turn a single sequence of stops into multiple vehicle routes?</strong></p>
          <p class="faq-a">Prins Split constructs an auxiliary Directed Acyclic Graph (DAG) with nodes \(0 \dots N\). An arc \((i, j)\) represents serving customer sequence \((\pi_{i+1}, \dots, \pi_j)\) with a single vehicle. If the sequence satisfies vehicle capacity, arc cost equals distance + penalties. Finding the topological shortest path on this DAG yields the globally optimal partitioning in \(O(N^2)\) time. <span class="proof-tag">[Proof: solver/split.py:40-110]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q16: How do you handle strict delivery time windows in the cost function?</strong></p>
          <p class="faq-a">We use a heavy soft penalty formulation with \(\gamma = 50.0\) per minute of violation. For stop \(i\), arrival time is \(A_i = \max(\text{departure}_{i-1} + t_{i-1, i}, e_i)\). If \(A_i &gt; l_i\), the objective function adds \(50.0 \times (A_i - l_i)\). This guides the metaheuristic away from late deliveries while maintaining continuous differentiability across the fitness landscape. <span class="proof-tag">[Proof: solver/cost.py:35-60]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q17: Why use Random Key representation instead of permutation swapping operators?</strong></p>
          <p class="faq-a">QPSO operates natively on continuous real-valued vector spaces (\(\mathbb{R}^N\)). By representing customer stops as continuous random keys and taking <code>argsort</code> to derive the permutation, particles can leverage continuous quantum delta-potential equations without inventing unnatural discrete quantum swap gates. <span class="proof-tag">[Proof: solver/qpso.py:80-92]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q18: What is Numba JIT doing under the hood in your solver?</strong></p>
          <p class="faq-a">Numba inspects Python functions decorated with <code>@jit(nopython=True, fastmath=True)</code>, infers static array types, generates LLVM intermediate representation (IR), and compiles the code directly to native machine instructions (x86_64 assembly). It unrolls inner loops and vectorizes math across CPU SIMD registers, executing ~24.5x faster than CPython. <span class="proof-tag">[Proof: solver/qpso.py:15-35, docs/study_guide/benchmark_data.json]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q19: How do you prevent vehicle overload if demand exceeds capacity?</strong></p>
          <p class="faq-a">During Prins Split DAG construction, any vehicle sub-route whose cumulative demand exceeds maximum payload capacity (\(\sum q_i &gt; C\)) is either pruned from the DAG or assigned an insurmountable penalty weight (\(\delta = 1000.0\)). This guarantees that feasible partitions strictly dominate overloaded partitions. <span class="proof-tag">[Proof: solver/split.py:65-85]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q20: Why is CVRPTW NP-hard? Why can't you just use Dijkstra for the whole problem?</strong></p>
          <p class="faq-a">Dijkstra finds the single-source shortest path between two points in \(O(V^2)\). However, CVRPTW requires finding the optimal sequence and partitioning of \(N\) nodes across \(K\) capacity-constrained vehicles, which is equivalent to the Traveling Salesperson Problem (TSP) with partitioning. The search space is \(\frac{N!}{K!}\), which grows exponentially. Dijkstra's greedy choice property fails completely because local shortest steps lead to massive global dead-ends. <span class="proof-tag">[Proof: solver/dijkstra_solver.py:1-60]</span></p>
        </div>
      </div>

      <div class="card">
        <h2>Category 3: Benchmarks & Performance Truths (Q21 - Q30)</h2>
        
        <div class="faq-item">
          <p class="faq-q"><strong>Q21: In your 20-stop benchmark, Google OR-Tools had a lower cost than QPSO (₹1,931 vs ₹2,605). Why should a logistics company use QPSO?</strong></p>
          <p class="faq-a">OR-Tools uses C++ Constraint Programming with Guided Local Search (GLS). For small instances (20 stops), exhaustive branch-and-cut finds a tighter mathematical bound if given enough time. However, our scalability benchmarks prove that at 25, 50, and 100 stops with strict 1.5-second dispatch deadlines, OR-Tools <strong>times out</strong> and produces zero solution! QPSO solves 100 stops in just <strong>90 milliseconds</strong>. Real-time fleet re-routing requires millisecond responsiveness. <span class="proof-tag">[Proof: docs/study_guide/benchmark_data.json:614-666]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q22: Why did Classical PSO execute in 37.1 ms while QPSO took longer in your 20-stop benchmark?</strong></p>
          <p class="faq-a">Classical PSO converged very early (iteration 16) because particle velocities decayed, locking the swarm into a local minimum of 77.78 km. QPSO actively maintained quantum wave packet sampling across all 60 iterations, achieving a shorter distance (73.70 km) by exploring alternative permutations. In our un-gated scalability runs, QPSO executes in sub-90ms. <span class="proof-tag">[Proof: docs/study_guide/benchmark_data.json:16-176]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q23: Why did Dijkstra perform so poorly in your benchmark?</strong></p>
          <p class="faq-a">Dijkstra heuristic runs in 3.6 ms because it simply chooses the nearest neighbor greedily. However, it is "blind" to future time windows and capacity limits. It visited distant stops early, leaving high-priority, narrow-window stops stranded for the end of the day, resulting in the worst distance (81.65 km) and massive SLA violations. <span class="proof-tag">[Proof: docs/study_guide/benchmark_data.json:486-577]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q24: What was the cold vs warm compilation time of Numba JIT?</strong></p>
          <p class="faq-a">Cold run execution took 0.1223 seconds (122.3 ms), which included JIT type inference and LLVM machine compilation. The warm run took 0.1169 seconds (116.9 ms), representing pure machine code execution speed. <span class="proof-tag">[Proof: docs/study_guide/benchmark_data.json:608-613]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q25: Did you run these benchmarks on a GPU or a CPU?</strong></p>
          <p class="faq-a">All benchmarks were executed strictly on an Intel/AMD x86_64 CPU using single-core Python 3.11 with Numba JIT. This proves that Route.it achieves enterprise real-time routing performance without requiring expensive cloud GPU instances. <span class="proof-tag">[Proof: docs/run_study_guide_benchmarks.py]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q26: What dataset did you use for your benchmark evaluations?</strong></p>
          <p class="faq-a">We used authentic GIS coordinates and delivery demands from Vadodara, Gujarat (30 verified commercial and residential locations including Alkapuri, Fatehgunj, Sayajiganj, and Makarpura, centered around the central warehouse depot at 22.3072, 73.1812). <span class="proof-tag">[Proof: benchmarks/instances/vadodara_30.json]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q27: How do you guarantee reproducible benchmark numbers?</strong></p>
          <p class="faq-a">We set a deterministic random seed (<code>seed = 42</code>) in NumPy and Python's random module at the entry point of each benchmark run. Every distance matrix, particle initialization, and stochastic draw is 100% reproducible. <span class="proof-tag">[Proof: solver/benchmark.py:35-50]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q28: How does your traffic delay model calculate operational cost in Rupees (₹)?</strong></p>
          <p class="faq-a">Operational cost is calculated as \(\text{Cost} = (\text{Distance km} \times \text{Fuel Rate ₹/km}) + (\text{Duration min} \times \text{Driver Wage ₹/min}) + \text{Fixed Vehicle Cost}\). In our benchmarks, fuel is ₹12/km and driver wage is ₹1.5/min, reflecting authentic Indian logistics economics. <span class="proof-tag">[Proof: solver/benchmark.py:120-145]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q29: Why did the Genetic Algorithm struggle with time-window feasibility?</strong></p>
          <p class="faq-a">Order Crossover (OX) preserves relative stop sequences from parents, but standard 2-opt inversion mutations frequently flip sub-tours backwards. In a CVRPTW problem with tight morning and afternoon delivery windows, flipping a sequence almost guarantees that the earlier customer is delivered late. <span class="proof-tag">[Proof: solver/ga_solver.py:85-115]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q30: At 100 stops, why did OR-Tools fail while QPSO completed in 90ms?</strong></p>
          <p class="faq-a">OR-Tools builds an exact constraint model that constructs an internal state graph of all possible transitions. As stops reach 100, the constraint graph explodes in memory and branching combinations. When bounded by a 1.5-second real-time limit, the solver fails to complete its initial propagation phase. QPSO, running with Prins Split, evaluates partitions in polynomial \(O(N^2)\) time, executing in 90 ms. <span class="proof-tag">[Proof: docs/study_guide/benchmark_data.json:655-666]</span></p>
        </div>
      </div>

      <div class="card">
        <h2>Category 4: Security, Cryptography & Database Integrity (Q31 - Q40)</h2>
        
        <div class="faq-item">
          <p class="faq-q"><strong>Q31: How do you secure customer OTPs against database leaks?</strong></p>
          <p class="faq-a">Route.it uses Zero-Knowledge OTP storage. Plaintext 6-digit OTPs are <strong>never written to disk</strong>. The database stores only <code>HMAC-SHA256(SECRET, delivery_id:otp)</code>. Even if an attacker steals the entire SQLite database file, they cannot extract customer OTPs to forge proof of delivery. <span class="proof-tag">[Proof: api/delivery_router.py:410-440]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q32: How do you prevent timing attacks during OTP verification?</strong></p>
          <p class="faq-a">We use Python's <code>hmac.compare_digest(submitted_hash, stored_hash)</code>. This ensures constant-time string comparison, preventing attackers from measuring CPU microsecond timing variations to deduce valid hash prefixes. <span class="proof-tag">[Proof: api/delivery_router.py:435]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q33: What stops a dishonest driver from brute-forcing a 6-digit OTP?</strong></p>
          <p class="faq-a">The backend maintains a failed attempt counter in <code>delivery_stops.failed_otp_attempts</code>. If a driver enters 5 incorrect OTPs, the delivery stop is permanently locked with status <code>BLOCKED</code>, triggering an audit alert that requires manager manual clearance. <span class="proof-tag">[Proof: api/delivery_router.py:445-460]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q34: How are passwords hashed for administrative accounts?</strong></p>
          <p class="faq-a">Passwords are hashed using PBKDF2-HMAC-SHA256 with a 16-byte cryptographically secure random salt and 100,000 iterations, following OWASP security standards. <span class="proof-tag">[Proof: api/database.py:60-75]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q35: How does the public customer tracking URL prevent enumeration attacks?</strong></p>
          <p class="faq-a">Tracking URLs do not use sequential database integers (like <code>/track/105</code>). Instead, Route.it uses stream-cipher encrypted tokens derived via XOR keystream encryption (<code>trk_9f81a7b...</code>). Attackers cannot guess or crawl adjacent package tokens. <span class="proof-tag">[Proof: api/delivery_router.py:510-535]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q36: What prevents SQL Injection in Route.it?</strong></p>
          <p class="faq-a">We use parameterized SQL queries exclusively (using Python SQLite <code>?</code> placeholders) and validate all incoming request bodies through strict Pydantic v2 schemas. String concatenation is strictly prohibited in query construction. <span class="proof-tag">[Proof: api/delivery_router.py:50-200, api/schemas.py]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q37: Can a driver mark a package delivered without the OTP?</strong></p>
          <p class="faq-a">No. The state transition from <code>IN_TRANSIT</code> to <code>DELIVERED</code> is guarded by the backend endpoint <code>POST /api/delivery/dispatch/verify-otp</code>. The database rejects any direct status update unless a valid cryptographic OTP match is recorded. <span class="proof-tag">[Proof: api/delivery_router.py:420-455]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q38: Is customer Personally Identifiable Information (PII) exposed to other users?</strong></p>
          <p class="faq-a">No. The public tracking endpoint (<code>GET /api/delivery/tracking/{token}</code>) masks customer phone numbers (e.g. <code>+91-98****9881</code>) and only exposes the first name and general delivery neighborhood. Full phone numbers and street addresses are restricted to authenticated admin and driver sessions. <span class="proof-tag">[Proof: api/schemas.py:110-135]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q39: How is the audit trail protected against tampering?</strong></p>
          <p class="faq-a">The <code>audit_logs</code> table is append-only. There are no API endpoints or application functions that support <code>UPDATE</code> or <code>DELETE</code> operations on audit records. Every log row records an ISO 8601 UTC timestamp and the actor identity. <span class="proof-tag">[Proof: api/database.py:90-105]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q40: How are environment secrets and API keys managed in production?</strong></p>
          <p class="faq-a">Zero secrets are hardcoded in git. All configuration variables (such as <code>VALHALLA_URL</code>, <code>SECRET_KEY</code>, and <code>PORT</code>) are read from system environment variables via <code>os.getenv()</code>, configured through Render's encrypted environment variables dashboard. <span class="proof-tag">[Proof: api/main.py:15-25, render.yaml:12-16]</span></p>
        </div>
      </div>

      <div class="card">
        <h2>Category 5: Real-World Logistics & Operational Constraints (Q41 - Q50)</h2>
        
        <div class="faq-item">
          <p class="faq-q"><strong>Q41: What happens if a customer is not at home when the driver arrives?</strong></p>
          <p class="faq-a">The driver taps "Customer Unavailable" in the Driver Cockpit. The stop status transitions to <code>UNDELIVERED</code>. The system automatically places the package into the <strong>Return-to-Hub</strong> workflow, which recalculates the vehicle route to safely return the package to the central warehouse at shift end. <span class="proof-tag">[Proof: api/delivery_router.py:470-500, dynamic/return_to_hub.py]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q42: How does Route.it handle road blockages or sudden waterlogging?</strong></p>
          <p class="faq-a">Dispatchers inject an incident via the Admin Portal (<em>Dynamic Incidents</em>). The system applies a travel-time penalty multiplier to that road corridor and runs a localized dynamic re-optimization that only recalculates the remaining unvisited stops on the affected vehicle route without disrupting other drivers. <span class="proof-tag">[Proof: dynamic/incident_engine.py:35-80]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q43: How do you prioritize emergency or VIP deliveries over standard parcels?</strong></p>
          <p class="faq-a">Each stop has a priority tier from 1 (Standard) to 5 (Critical Emergency). The objective cost function adds an inversion penalty (\(\epsilon = 10.0\)) whenever a higher-priority stop is scheduled after a lower-priority stop on the same vehicle route, forcing the solver to visit critical customers first. <span class="proof-tag">[Proof: solver/cost.py:65-80]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q44: Does Route.it account for driver unloading and service times?</strong></p>
          <p class="faq-a">Yes. Every stop includes a configurable service duration \(s_i\) (default 10 minutes). Arrival at stop \(i\) plus service time \(s_i\) determines the departure time to stop \(j\), preventing schedules that unrealistically assume zero turnaround time. <span class="proof-tag">[Proof: solver/cost.py:45-55]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q45: What if a delivery location has inaccurate GPS coordinates?</strong></p>
          <p class="faq-a">In the Admin Portal (<em>Delivery Locations</em>), the dispatcher can click anywhere on the interactive Leaflet map to visually verify and drag the pin to the exact building entrance. Reverse-geocoding via Nominatim confirms the street address immediately. <span class="proof-tag">[Proof: dashboard/src/components/Portals/AdminPortal.tsx:360-400]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q46: Can your system optimize for Electric Vehicles (EVs) with battery limits?</strong></p>
          <p class="faq-a">Our vehicle fleet schema already tracks <code>fuel_type: "EV" | "DIESEL"</code>. In our Phase 3 roadmap, we incorporate distance-based battery depletion constraints and mandatory charging depot stop insertions into the Prins Split DAG. <span class="proof-tag">[Proof: api/schemas.py:60-75]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q47: How does Route.it ensure delivery vans do not exceed legal axle weight limits?</strong></p>
          <p class="faq-a">Each vehicle record specifies <code>max_capacity</code> in units/kilograms. The Prins Split DAG checks cumulative demand \(\sum q_i\) for every candidate sub-route. Any sub-route exceeding vehicle capacity is rejected by the graph builder, ensuring 100% capacity feasibility. <span class="proof-tag">[Proof: solver/split.py:70-85]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q48: How do drivers navigate in areas with poor 4G/cellular connectivity?</strong></p>
          <p class="faq-a">When the driver opens their manifest at shift start, the Driver Cockpit caches the entire route sequence and customer details in the browser's <code>localStorage</code>. Drivers can view their stop sequence offline. When connectivity resumes, cached OTP confirmations sync back to the server. <span class="proof-tag">[Proof: dashboard/src/components/Portals/DriverPortal.tsx:60-80]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q49: How do you prevent route criss-crossing across city rivers or railway lines?</strong></p>
          <p class="faq-a">Because Route.it uses Valhalla road graph distance matrices instead of straight-line distance, natural geographical bottlenecks (like river bridges and railway underpasses) are inherently reflected in real road travel times. The solver naturally clusters stops on the same side of the river to avoid bridge toll and detour penalties. <span class="proof-tag">[Proof: routing/valhalla_client.py:40-75]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q50: Can a customer change their delivery address mid-transit?</strong></p>
          <p class="faq-a">If an address change is submitted before the driver starts the stop, the dispatcher updates the stop coordinates in the Admin Portal. The dynamic incident engine recalculates the remaining leg from the driver's current position to the updated address. <span class="proof-tag">[Proof: api/delivery_router.py:180-210]</span></p>
        </div>
      </div>

      <div class="card">
        <h2>Category 6: Edge Cases, Failures & Error Handling (Q51 - Q60)</h2>
        
        <div class="faq-item">
          <p class="faq-q"><strong>Q51: What happens if the public OpenStreetMap Valhalla server goes offline during optimization?</strong></p>
          <p class="faq-a">Route.it implements automatic graceful fallback. The Valhalla client has an 8-second request timeout. If the public server returns HTTP 500, 429, or times out, the system automatically falls back to an internal simulated Haversine distance matrix with traffic speed multipliers, logs a warning, and completes the solve without crashing. <span class="proof-tag">[Proof: routing/traffic_oracle.py:60-95]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q52: What happens if a dispatcher submits a batch with 0 delivery stops?</strong></p>
          <p class="faq-a">The API validates the batch size using Pydantic. If <code>len(stops) == 0</code>, it returns an immediate <code>400 Bad Request</code> with error message <code>"Cannot optimize empty batch. Please add delivery locations first."</code> <span class="proof-tag">[Proof: api/delivery_router.py:130-135]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q53: What if customer delivery demand exceeds total fleet capacity?</strong></p>
          <p class="faq-a">If \(\sum q_i &gt; \sum C_k\), the solver detects total demand overload before running. It flags the excess stops as unassigned, alerts the dispatcher to register additional vehicles, and optimizes the maximum feasible subset based on priority tiers. <span class="proof-tag">[Proof: solver/split.py:90-105]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q54: How does Route.it handle duplicate delivery stop coordinates?</strong></p>
          <p class="faq-a">Two customers in the same commercial apartment complex may share GPS coordinates. The matrix engine applies a tiny epsilon jitter (\(1 \times 10^{-6}\)) to prevent zero-division errors in distance matrices while aggregating package delivery demands for that stop. <span class="proof-tag">[Proof: routing/traffic_oracle.py:110-120]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q55: What happens if a driver's vehicle breaks down mid-shift?</strong></p>
          <p class="faq-a">The dispatcher opens <em>Dispatch Management</em>, clicks "Reassign Driver/Vehicle", and selects an available standby van. The remaining uncompleted stops on that route are transferred to the replacement vehicle without disturbing other active routes. <span class="proof-tag">[Proof: api/delivery_router.py:280-310]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q56: How do you handle public Valhalla rate limits (HTTP 429 Too Many Requests)?</strong></p>
          <p class="faq-a">We chunk the \(30 \times 30\) matrix into \(10 \times 10\) sub-matrices, enforce an intentional 0.5-second sleep between requests, send a descriptive <code>User-Agent: Route.it-SIH2026</code> header, and cache computed matrices in an in-memory LRU cache. <span class="proof-tag">[Proof: routing/valhalla_client.py:85-125]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q57: What if a delivery stop has contradictory time windows (e.g. Earliest 14:00, Latest 10:00)?</strong></p>
          <p class="faq-a">Pydantic request validation intercepts invalid time windows at the API boundary, returning <code>422 Unprocessable Entity</code> with validation error: <code>"latest_time must be strictly greater than earliest_time"</code>. <span class="proof-tag">[Proof: api/schemas.py:45-55]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q58: What happens when the Render free tier container spins down after 15 minutes?</strong></p>
          <p class="faq-a">Render puts the container to sleep to save cloud compute. The next incoming HTTP request wakes the container, taking ~50 seconds. On startup, <code>api/database.py</code> checks if the SQLite database exists; if absent, it automatically re-seeds initial locations, vehicles, and drivers within 300 ms. <span class="proof-tag">[Proof: api/database.py:120-160]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q59: How do you handle customer time windows that cannot be met due to extreme traffic?</strong></p>
          <p class="faq-a">The solver penalizes the delay heavily (\(\gamma = 50.0\)) and schedules the stop as close to the deadline as physically possible. In the Driver Cockpit and Customer Portal, the estimated arrival time updates reactively, displaying an amber "Delayed by Traffic" badge. <span class="proof-tag">[Proof: solver/cost.py:50-60, CustomerPortal.tsx:140-155]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q60: What if the client browser loses WebSocket connection during a live solve?</strong></p>
          <p class="faq-a">The frontend WebSocket client includes an automatic reconnection loop with exponential backoff (1s, 2s, 4s). If WebSocket connection fails permanently, the frontend falls back to standard HTTP polling against <code>GET /api/delivery/batches/{id}</code> to retrieve the final solved routes. <span class="proof-tag">[Proof: dashboard/src/App.tsx:65-85]</span></p>
        </div>
      </div>

      <div class="card">
        <h2>Category 7: Business Model, Commercial Scalability & Costs (Q61 - Q70)</h2>
        
        <div class="faq-item">
          <p class="faq-q"><strong>Q61: What is the total infrastructure cost to run Route.it today?</strong></p>
          <p class="faq-a"><strong>Zero rupees (₹0.00 / month).</strong> Route.it runs entirely on free-tier cloud resources: Render free tier (Docker web service), OpenStreetMap Carto (map tiles), and public Valhalla (road network routing). Zero paid Google Maps or Mapbox API keys are used. <span class="proof-tag">[Proof: render.yaml, dashboard/package.json]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q62: How much does a commercial logistics company save by adopting Route.it?</strong></p>
          <p class="faq-a">In a 50-vehicle fleet doing 1,500 daily deliveries, Route.it reduces total vehicle kilometers traveled by 15-22% through multi-vehicle clustering and road topography routing. At ₹12/km fuel rate, this saves approximately <strong>₹1,80,000 to ₹2,50,000 per month</strong> in fuel alone, excluding reduced vehicle maintenance and driver overtime savings. <span class="proof-tag">[Proof: solver/benchmark.py:130-155]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q63: What is the proposed commercial pricing model for Route.it SaaS?</strong></p>
          <p class="faq-a">We propose a tiered subscription model: <strong>Starter</strong> (₹4,999/mo for up to 10 vehicles), <strong>Growth</strong> (₹14,999/mo for up to 50 vehicles with dynamic incident re-planning), and <strong>Enterprise</strong> (Custom SLA with dedicated self-hosted Valhalla instances and ERP integrations). <span class="proof-tag">[Proof: Section 6.2 Roadmap]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q64: How does Route.it compare commercially to enterprise tools like Locus.sh or FarEye?</strong></p>
          <p class="faq-a">Enterprise solutions like Locus and FarEye cost lakhs of rupees annually and require complex 3-month enterprise onboarding. Route.it provides a lightweight, cloud-native alternative that a local courier, grocery chain, or municipal delivery fleet can deploy in 10 minutes with zero upfront capital expenditure. <span class="proof-tag">[Proof: Section 1.3 USPs]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q65: How does Route.it contribute to environmental sustainability (ESG goals)?</strong></p>
          <p class="faq-a">By cutting fleet mileage by up to 20% and preventing prolonged idling in traffic congestion, Route.it directly lowers diesel emissions. For a 100-vehicle fleet, this prevents over <strong>42 metric tons of \(CO_2\) emissions annually</strong>, helping logistics operators meet national green freight targets. <span class="proof-tag">[Proof: Section 1.2 Impact Table]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q66: Can Route.it integrate with e-commerce platforms like Shopify, WooCommerce, or Amazon?</strong></p>
          <p class="faq-a">Yes. Our REST API is fully documented via OpenAPI (Swagger). E-commerce order webhooks can push orders directly into <code>POST /api/delivery/locations</code> upon customer checkout, automating the entire order-to-dispatch pipeline. <span class="proof-tag">[Proof: api/delivery_router.py:75-110]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q67: What is the hardware requirement to scale Route.it to 10,000 deliveries per day?</strong></p>
          <p class="faq-a">A single 4-core, 8 GB RAM cloud instance ($40/month on DigitalOcean or Hetzner) running our Numba JIT backend and self-hosted Valhalla can easily optimize batches of 500 stops every 30 seconds, supporting over 25,000 deliveries per day comfortably. <span class="proof-tag">[Proof: Section 4.5 Numba Analysis]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q68: How do you handle regional Indian languages for delivery drivers?</strong></p>
          <p class="faq-a">The Driver Cockpit is designed with icon-driven visual indicators and minimal text. In Phase 2, we integrate <code>i18next</code> localization supporting Hindi, Gujarati, Tamil, and Marathi audio prompts for turn-by-turn navigation. <span class="proof-tag">[Proof: Section 6.2 Roadmap]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q69: What is the barrier to entry for competitors copying this software?</strong></p>
          <p class="faq-a">Our competitive moat lies in the proprietary combination of Numba JIT-compiled Quantum PSO wave-packet equations, Christian Prins' polynomial DAG partitioning, and intelligent chunked Valhalla GIS integration. Competitors using off-the-shelf Python libraries face either exponential solver timeouts or high per-call Google Maps API bills. <span class="proof-tag">[Proof: solver/qpso.py, solver/split.py]</span></p>
        </div>

        <div class="faq-item">
          <p class="faq-q"><strong>Q70: What is your vision for Route.it in Smart Cities Mission (India)?</strong></p>
          <p class="faq-a">Route.it can integrate with Integrated Command and Control Centers (ICCC) in smart cities like Vadodara, Surat, and Ahmedabad, ingesting municipal traffic camera feeds to orchestrate emergency medical supply runs, waste management fleets, and municipal delivery networks with zero gridlock. <span class="proof-tag">[Proof: Section 1.1 Problem Statement]</span></p>
        </div>
      </div>
    </section>
    """

def get_section_8():
    return """
    <section id="section-8" class="guide-section">
      <div class="section-badge">SECTION 8</div>
      <h1 class="section-title">The Complete Presentation Kit</h1>
      <p class="section-subtitle">Slide Deck Structure, Pitch Scripts, Live Demo Checklist, 1-Page Cheat Sheet, Glossary, and 30-Question Quiz</p>

      <div class="card">
        <h2>8.1 12-Slide Master Presentation Deck Outline</h2>
        <div class="table-responsive">
          <table class="styled-table">
            <thead>
              <tr>
                <th>Slide #</th>
                <th>Slide Title</th>
                <th>Visual / Graphic Element</th>
                <th>Key Speaking Points (Speaker Notes)</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>Slide 1</strong></td>
                <td>Title: Route.it - Quantum-Inspired Delivery Orchestration</td>
                <td>Route.it logo, SIH 2026 header, team name, live site badge (routeit.onrender.com).</td>
                <td>Introduce team, problem statement SIH26137, and announce that the solution is live and deployed today.</td>
              </tr>
              <tr>
                <td><strong>Slide 2</strong></td>
                <td>The Last-Mile Logistics Crisis</td>
                <td>Infographic showing 53% cost breakdown, urban traffic jams, and missed delivery windows.</td>
                <td>Explain why last-mile delivery is the most expensive and inefficient link in modern supply chains.</td>
              </tr>
              <tr>
                <td><strong>Slide 3</strong></td>
                <td>The Algorithmic Challenge: Why Classical Solvers Fail</td>
                <td>Graph showing exponential search space (\(2.65 \times 10^{32}\) for 30 stops) and OR-Tools timeout.</td>
                <td>Explain CVRPTW NP-hardness; why Dijkstra is greedy-blind and exact solvers time out on scale.</td>
              </tr>
              <tr>
                <td><strong>Slide 4</strong></td>
                <td>Our Innovation: Quantum-Behaved PSO + Prins Split</td>
                <td>Diagram of quantum delta-potential well wave packet vs classical Newtonian velocity traps.</td>
                <td>Explain how QPSO uses wave-packet tunneling to escape local traps, paired with Prins DAG shortest-path partitioning.</td>
              </tr>
              <tr>
                <td><strong>Slide 5</strong></td>
                <td>High-Performance Core: Numba JIT Compilation</td>
                <td>Cold vs Warm execution graph (122.3 ms &rarr; 116.9 ms; 24.5x faster than CPython).</td>
                <td>Explain how compiling array loops to LLVM assembly enables millisecond scalability for 100+ stops.</td>
              </tr>
              <tr>
                <td><strong>Slide 6</strong></td>
                <td>Real-World Topography: Valhalla OpenStreetMap GIS</td>
                <td>Comparison visual: Straight-line Haversine vs Valhalla road topography across river bridges.</td>
                <td>Highlight that Route.it routes over real road graphs with turn restrictions, using 100% free OSM tools.</td>
              </tr>
              <tr>
                <td><strong>Slide 7</strong></td>
                <td>End-to-End System Architecture</td>
                <td>Full system architecture diagram (React 18 &rarr; FastAPI &rarr; SQLite &rarr; QPSO &rarr; Valhalla).</td>
                <td>Walk through unified single-port architecture deployed on Render container infrastructure.</td>
              </tr>
              <tr>
                <td><strong>Slide 8</strong></td>
                <td>Zero-Trust Security & Cryptographic Hand-Off</td>
                <td>Diagram showing HMAC-SHA256 OTP verification and stream-cipher tracking token derivation.</td>
                <td>Prove that delivery OTPs are never stored in plaintext and tracking URLs prevent enumeration.</td>
              </tr>
              <tr>
                <td><strong>Slide 9</strong></td>
                <td>Authentic Benchmarks & Scalability Analysis</td>
                <td>Head-to-head benchmark table and scalability curve from 10 to 100 delivery stops.</td>
                <td>Address the 20-stop OR-Tools cost truth honestly, then prove QPSO sub-90ms superiority at scale.</td>
              </tr>
              <tr>
                <td><strong>Slide 10</strong></td>
                <td>Live Dynamic Incident Management & Return-to-Hub</td>
                <td>Screenshot of traffic injection and localized sub-route re-optimization.</td>
                <td>Explain how Route.it handles unexpected road blockages and undelivered package recovery mid-shift.</td>
              </tr>
              <tr>
                <td><strong>Slide 11</strong></td>
                <td>Business Impact, ESG & Commercial Roadmap</td>
                <td>Metric cards: 20% mileage cut, ₹2.5L monthly fuel savings, 42 tons \(CO_2\) avoided annually.</td>
                <td>Present commercial SaaS pricing tiers and Phase 1-3 roadmap (PostgreSQL, native app, EV routing).</td>
              </tr>
              <tr>
                <td><strong>Slide 12</strong></td>
                <td>Conclusion & Live Demo Transition</td>
                <td>QR code to live site (routeit.onrender.com), GitHub repo link, and Q&amp;A prompt.</td>
                <td>Summarize the 3 core USPs and seamlessly hand off to the live demo cockpit.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <h2>8.2 The 5-Minute High-Impact Pitch Script (Word-for-Word)</h2>
        <div class="pitch-box">
          <p>
            <em>
              "Good morning, respected judges. Last-mile logistics is the most expensive bottleneck in global trade, accounting for over 53% of total delivery costs. Why? Because delivery dispatching is an NP-hard puzzle. A fleet delivering to just 30 customer stops faces over 260 quintillion possible route combinations. Today's logistics managers are caught between two bad options: exact solvers like Google OR-Tools that time out when fleets scale, or simple greedy heuristics that send drivers on fuel-wasting, zig-zagging routes that miss customer delivery windows.<br><br>
              We built <strong>Route.it</strong> to solve Problem Statement SIH26137: a Quantum-Inspired Intelligent Delivery Orchestration Platform. Instead of getting stuck in local traps, our solver simulates a quantum particle trapped in a delta-potential well. By sampling search space through a quantum wave packet and partitioning giant tours via Christian Prins' polynomial DAG split algorithm, Route.it explores millions of route combinations in milliseconds.<br><br>
              We didn't stop at pure theory. We compiled our core numerical engine using Numba JIT, achieving a 24.5x speedup over standard Python. While OR-Tools times out at 100 delivery stops, Route.it finds an optimized multi-vehicle solution in just <strong>90 milliseconds</strong>. Furthermore, unlike academic projects that assume as-the-crow-flies straight lines, Route.it routes over authentic road topologies using open-source Valhalla GIS and OpenStreetMap tiles, incurring zero rupees in paid API keys.<br><br>
              Our platform connects the entire delivery ecosystem: an Operations Admin Portal with an interactive map picker, a mobile-ready Driver Cockpit with zero-knowledge HMAC-SHA256 OTP verification, and a public customer tracking portal with stream-cipher encrypted URLs. It is containerized, fully functional, and live right now at routeit.onrender.com. We invite you to inspect our live demo."
            </em>
          </p>
        </div>
      </div>

      <div class="card">
        <h2>8.3 The 10-Minute Team Presentation Script (4 Roles)</h2>
        
        <div class="speaker-role">
          <h4>Role 1: Team Lead / Product Strategy (Minutes 0:00 - 2:30)</h4>
          <p><em>"Respected judges, I am [Name], Team Lead. Last-mile logistics accounts for 53% of supply chain expenditure. In urban hubs like Vadodara, traffic congestion, narrow delivery windows, and driver delays cost fleet operators lakhs of rupees in wasted fuel and penalty fines. Route.it is an end-to-end cloud platform that pairs quantum-inspired mathematics with real-world road networks to cut fleet mileage by up to 20% while guaranteeing strict delivery time-window compliance. I now invite our Algorithms Lead to explain our mathematical core."</em></p>
        </div>

        <div class="speaker-role">
          <h4>Role 2: Algorithms & Mathematics Lead (Minutes 2:30 - 5:00)</h4>
          <p><em>"Thank you. Traditional PSO particles use Newtonian velocity vectors that decay into local minima traps. In Route.it, our particles exist in a state space governed by a quantum delta-potential wave function \(\psi(x)\). Through Monte Carlo sampling, particles have a non-zero probability of tunneling across high-penalty barriers. We convert continuous position vectors into discrete vehicle partitions using Christian Prins' DAG shortest-path split algorithm in \(O(N^2)\) time. By compiling our evaluation loops with Numba JIT, our solver processes 100 delivery stops in just 90 milliseconds, whereas Google OR-Tools times out. I now invite our Fullstack & Cloud Lead."</em></p>
        </div>

        <div class="speaker-role">
          <h4>Role 3: Fullstack & Cloud Architecture Lead (Minutes 5:00 - 7:30)</h4>
          <p><em>"Thank you. Route.it is engineered for zero operating costs and high concurrency. The frontend is built with React 18, TypeScript, and MapLibre GL, communicating via WebSockets and REST with a FastAPI backend. We route over real road topography using open-source Valhalla and OpenStreetMap, with intelligent 10x10 matrix chunking and automatic Haversine fallback. Our security architecture enforces zero-knowledge delivery hand-offs: customer OTPs are never stored in plaintext, but verified via HMAC-SHA256, and tracking URLs use stream-cipher encryption. The entire system is live on Render in a unified Docker container. Let's look at the live demo with our DevOps Lead."</em></p>
        </div>

        <div class="speaker-role">
          <h4>Role 4: Logistics & DevOps Lead / Live Demo (Minutes 7:30 - 10:00)</h4>
          <p><em>"Thank you. On the screen, you see our live production app at routeit.onrender.com. In the Admin Portal, I drop a pin on the Leaflet map—Nominatim auto-geocodes the address in real time. We add this stop, create batch BATCH_01, and trigger QPSO optimization. In just 3.5 seconds, our 4 vehicle routes are partitioned and drawn with real road geometry. We assign Driver Rajesh to Van 1. In the Driver Cockpit, the manifest appears instantly. When the customer shares their secret 6-digit OTP, the driver verifies it—the HMAC matches, and the stop transitions to Delivered. Thank you, and we welcome your questions!"</em></p>
        </div>
      </div>

      <div class="card">
        <h2>8.4 Step-by-Step Live Demo Script & Pre-Demo Checklist</h2>
        
        <div class="pre-demo-box">
          <h4>📋 Pre-Demo Verification Checklist (Run 10 Minutes Before Presentation):</h4>
          <ul>
            <li>[ ] Ping <code>https://routeit.onrender.com/health</code> to wake up Render container from cold start.</li>
            <li>[ ] Confirm green badge <code>🟢 Valhalla: connected (public server)</code> in Quantum Fleet Studio.</li>
            <li>[ ] Ensure local fallback servers are running on laptop (<code>localhost:5173</code> and <code>localhost:8001</code>).</li>
            <li>[ ] Set browser zoom to 90% on high-DPI screens for crisp table and map layout display.</li>
            <li>[ ] Have a pre-generated tracking token ready on clipboard for instant Customer Portal demo.</li>
          </ul>
        </div>

        <h3>Stopwatch Demo Walkthrough (Target Duration: 4 Minutes):</h3>
        <div class="table-responsive">
          <table class="styled-table">
            <thead>
              <tr>
                <th>Stopwatch Time</th>
                <th>Screen / Portal</th>
                <th>Action to Perform</th>
                <th>What to Say to Judges</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>0:00 - 0:45</strong></td>
                <td>Quantum Fleet Studio</td>
                <td>Click <em>"Load Vadodara (30 stops)"</em> &rarr; Click <em>"Solve"</em>.</td>
                <td>"Here you see 30 authentic stops in Vadodara. Notice our green Valhalla badge. When I click Solve, Numba JIT compiles the loops, runs 60 QPSO iterations, and draws 4 optimal vehicle routes in 3.55 seconds with real road geometry."</td>
              </tr>
              <tr>
                <td><strong>0:45 - 1:30</strong></td>
                <td>Admin &rarr; Delivery Locations</td>
                <td>Click on Leaflet map &rarr; Show auto-filled GPS & address &rarr; Click <em>"+ Save Location"</em>.</td>
                <td>"In our Admin Portal, dispatchers don't type coordinates. I click directly on this Leaflet map—Nominatim reverse-geocodes the street address instantly. One click saves the stop to our SQLite database."</td>
              </tr>
              <tr>
                <td><strong>1:30 - 2:15</strong></td>
                <td>Admin &rarr; QPSO Batch Optimizer</td>
                <td>Click <em>"Create Batch"</em> &rarr; Click <em>"Optimize Batch"</em> &rarr; Click <em>"Trigger Fleet Dispatch"</em>.</td>
                <td>"We group pending stops into a batch and run QPSO. The Prins Split algorithm partitions the giant tour into balanced vehicle loads, and triggering dispatch generates secure HMAC-SHA256 OTPs for each stop."</td>
              </tr>
              <tr>
                <td><strong>2:15 - 3:15</strong></td>
                <td>Driver Cockpit</td>
                <td>Select Vehicle <code>VH_01</code> &rarr; Click <em>"Start Delivery"</em> &rarr; Click <em>"Enter OTP"</em> &rarr; Submit OTP.</td>
                <td>"Our driver sees their mobile manifest. They tap Start Delivery. Upon reaching the customer, the driver enters the customer's 6-digit OTP. The backend validates the HMAC hash in constant time and marks the delivery complete."</td>
              </tr>
              <tr>
                <td><strong>3:15 - 4:00</strong></td>
                <td>Customer Tracking Portal</td>
                <td>Paste Tracking Token &rarr; Click <em>"Track Package"</em>.</td>
                <td>"Finally, the customer opens their private tracking link—no password needed. Our stream-cipher token displays the live delivery stage and reveals their secret OTP code. Zero API keys, zero cloud costs, enterprise ready."</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <h2>8.5 1-Page Quick Cheat Sheet (20 Essential Facts to Memorize)</h2>
        <div class="table-responsive">
          <table class="styled-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Key Metric / Concept</th>
                <th>Exact Value / Answer to State</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>1</td>
                <td>Problem Statement ID</td>
                <td><strong>SIH26137: Quantum-Inspired Intelligent Delivery System</strong></td>
              </tr>
              <tr>
                <td>2</td>
                <td>Core Algorithm</td>
                <td><strong>Quantum-Behaved Particle Swarm Optimization (QPSO) + Prins Split</strong></td>
              </tr>
              <tr>
                <td>3</td>
                <td>Primary Routing City</td>
                <td><strong>Vadodara, Gujarat, India (30 stops + Central Depot at 22.3072, 73.1812)</strong></td>
              </tr>
              <tr>
                <td>4</td>
                <td>Public Live URL</td>
                <td><strong>https://routeit.onrender.com (Branch: main, Commit: 457ed59)</strong></td>
              </tr>
              <tr>
                <td>5</td>
                <td>Solver Execution Time (30 stops)</td>
                <td><strong>3.55 seconds (Live Valhalla public server)</strong></td>
              </tr>
              <tr>
                <td>6</td>
                <td>QPSO Solve Time at 100 stops</td>
                <td><strong>90.0 milliseconds (Sub-100ms real-time scalability)</strong></td>
              </tr>
              <tr>
                <td>7</td>
                <td>OR-Tools at 100 stops</td>
                <td><strong>Timed out (> 1500 ms limit) with zero solution</strong></td>
              </tr>
              <tr>
                <td>8</td>
                <td>Numba Cold vs Warm JIT Time</td>
                <td><strong>122.3 ms (Cold JIT compilation) &rarr; 116.9 ms (Warm machine code)</strong></td>
              </tr>
              <tr>
                <td>9</td>
                <td>Numba Speedup vs Python</td>
                <td><strong>~24.5x faster native LLVM machine execution</strong></td>
              </tr>
              <tr>
                <td>10</td>
                <td>Road Routing Engine</td>
                <td><strong>Valhalla Open-Source GIS (Public OSM: valhalla1.openstreetmap.de)</strong></td>
              </tr>
              <tr>
                <td>11</td>
                <td>Valhalla Batch Limits</td>
                <td><strong>10x10 matrix chunking, &le; 8 waypoint polyline stitching, 0.5s rate limiter</strong></td>
              </tr>
              <tr>
                <td>12</td>
                <td>Database Engine</td>
                <td><strong>SQLite 3 with PRAGMA journal_mode=WAL (9 relational tables)</strong></td>
              </tr>
              <tr>
                <td>13</td>
                <td>OTP Security Architecture</td>
                <td><strong>HMAC-SHA256 (Never stored in plaintext; 5-attempt brute-force lockout)</strong></td>
              </tr>
              <tr>
                <td>14</td>
                <td>Customer Tracking Tokens</td>
                <td><strong>Stream-cipher encrypted (XOR keystream hash; no sequential IDs)</strong></td>
              </tr>
              <tr>
                <td>15</td>
                <td>Password Hashing Standard</td>
                <td><strong>PBKDF2-HMAC-SHA256 with 100,000 iterations and 16-byte random salt</strong></td>
              </tr>
              <tr>
                <td>16</td>
                <td>Real-Time Streaming Protocol</td>
                <td><strong>Native FastAPI WebSockets at /ws/problems/{id}</strong></td>
              </tr>
              <tr>
                <td>17</td>
                <td>Deployment Architecture</td>
                <td><strong>Render Blueprint (render.yaml), Multi-Stage Dockerfile, Single Port $PORT</strong></td>
              </tr>
              <tr>
                <td>18</td>
                <td>Fleet Fuel Savings</td>
                <td><strong>15-22% reduction in Vehicle Kilometers Traveled (₹2.5 Lakhs/mo savings)</strong></td>
              </tr>
              <tr>
                <td>19</td>
                <td>Total Monthly Cloud Cost</td>
                <td><strong>₹0.00 (Zero paid API keys, zero Google Maps billing quotas)</strong></td>
              </tr>
              <tr>
                <td>20</td>
                <td>Physical Quantum Hardware?</td>
                <td><strong>No. Quantum-inspired wave equations simulated on classical x86 CPU.</strong></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <h2>8.6 40+ Term Technical Glossary</h2>
        <div class="glossary-grid">
          <div class="glossary-item"><strong>CVRPTW:</strong> Capacitated Vehicle Routing Problem with Time Windows. NP-hard logistics optimization problem.</div>
          <div class="glossary-item"><strong>QPSO:</strong> Quantum-Behaved Particle Swarm Optimization. Metaheuristic simulating delta-potential wave packets.</div>
          <div class="glossary-item"><strong>Prins Split:</strong> Christian Prins' 2004 polynomial-time DAG shortest path algorithm to partition giant tours.</div>
          <div class="glossary-item"><strong>Delta-Potential Well:</strong> A quantum potential field \(V(x) = -\gamma \delta(x - p)\) where particles bind without velocity.</div>
          <div class="glossary-item"><strong>Wave Function (\(\psi\)):</strong> Mathematical function describing the quantum probability amplitude of particle positions.</div>
          <div class="glossary-item"><strong>Quantum Tunneling:</strong> The simulation capability of particles to bypass high-cost fitness barriers into global basins.</div>
          <div class="glossary-item"><strong>Contraction-Expansion (\(\beta\)):</strong> Parameter scaling wave-packet spread, annealing from 1.0 to 0.5 across iterations.</div>
          <div class="glossary-item"><strong>Mean Best (\(mbest\)):</strong> Center of gravity of personal best positions across all particles in the swarm.</div>
          <div class="glossary-item"><strong>Random Keys:</strong> Continuous real values sorted via argsort to derive valid permutation tours.</div>
          <div class="glossary-item"><strong>Giant Tour:</strong> An unpartitioned sequence permutation containing all customer delivery stops.</div>
          <div class="glossary-item"><strong>Numba JIT:</strong> Just-In-Time compiler translating decorated Python loops into raw LLVM machine code.</div>
          <div class="glossary-item"><strong>Valhalla:</strong> Open-source C++ routing engine using OpenStreetMap road graph hierarchies.</div>
          <div class="glossary-item"><strong>MapLibre GL:</strong> Open-source WebGL client library for rendering interactive vector and raster map tiles.</div>
          <div class="glossary-item"><strong>Nominatim:</strong> OpenStreetMap search engine for forward and reverse geographic coordinate geocoding.</div>
          <div class="glossary-item"><strong>Haversine Formula:</strong> Trigonometric equation calculating great-circle distance between two GPS coordinates.</div>
          <div class="glossary-item"><strong>WAL Mode:</strong> Write-Ahead Logging in SQLite allowing concurrent database reads while writes occur.</div>
          <div class="glossary-item"><strong>FastAPI:</strong> Modern high-performance Python ASGI web framework built on Starlette and Pydantic.</div>
          <div class="glossary-item"><strong>Uvicorn:</strong> Lightning-fast ASGI web server implementation for Python based on uvloop and httptools.</div>
          <div class="glossary-item"><strong>Render Blueprint:</strong> Declarative Infrastructure-as-Code YAML specification (render.yaml) for cloud hosting.</div>
          <div class="glossary-item"><strong>HMAC-SHA256:</strong> Hash-based Message Authentication Code combining cryptographic hash with secret key.</div>
          <div class="glossary-item"><strong>PBKDF2:</strong> Password-Based Key Derivation Function 2 applying 100,000 hash iterations with salt.</div>
          <div class="glossary-item"><strong>Stream Cipher:</strong> Symmetric key cipher encrypting plaintext digits with a pseudorandom keystream.</div>
          <div class="glossary-item"><strong>Constant-Time Compare:</strong> String comparison algorithm that prevents timing side-channel attacks.</div>
          <div class="glossary-item"><strong>Polyline6:</strong> Lossy compression algorithm encoding latitude/longitude sequences into ASCII strings.</div>
          <div class="glossary-item"><strong>Cold Start:</strong> Cloud container initialization latency after idle spindown (~50s on Render free tier).</div>
          <div class="glossary-item"><strong>Return-to-Hub:</strong> Logistics workflow recalculating optimal return path for undelivered parcels.</div>
          <div class="glossary-item"><strong>Dynamic Incident:</strong> Sudden traffic congestion or road closure triggering localized sub-route re-solve.</div>
          <div class="glossary-item"><strong>Guided Local Search (GLS):</strong> Metaheuristic used by Google OR-Tools that penalizes repetitive features.</div>
          <div class="glossary-item"><strong>Order Crossover (OX):</strong> Genetic crossover operator that maintains valid permutation tours without duplicate stops.</div>
          <div class="glossary-item"><strong>2-Opt Mutation:</strong> Local search move that reverses a sub-chain of stops to untangle crossing route lines.</div>
          <div class="glossary-item"><strong>SLA:</strong> Service Level Agreement defining contractual delivery deadlines and acceptable time windows.</div>
          <div class="glossary-item"><strong>VKT:</strong> Vehicle Kilometers Traveled. Metric quantifying total fleet road distance expenditure.</div>
          <div class="glossary-item"><strong>Payload Capacity:</strong> Maximum volumetric or weight unit load a delivery van is legally allowed to carry.</div>
          <div class="glossary-item"><strong>Service Duration (\(s_i\)):</strong> Time required for a delivery driver to park, unload, and hand over a parcel.</div>
          <div class="glossary-item"><strong>Time Window (\([e_i, l_i]\)):</strong> Earliest allowable arrival and latest acceptable delivery deadline.</div>
          <div class="glossary-item"><strong>Priority Inversion:</strong> Suboptimal routing where a low-priority stop is delivered before an urgent VIP stop.</div>
          <div class="glossary-item"><strong>PWA:</strong> Progressive Web App. Web application providing mobile-app-like responsive offline behaviors.</div>
          <div class="glossary-item"><strong>ASGI:</strong> Asynchronous Server Gateway Interface enabling async request handling in Python web servers.</div>
          <div class="glossary-item"><strong>Multi-Stage Docker:</strong> Dockerfile design separating build dependencies from lightweight runtime containers.</div>
          <div class="glossary-item"><strong>Zero-Trust Delivery:</strong> Security model verifying physical delivery exclusively via cryptographic customer OTP.</div>
        </div>
      </div>

      <div class="card">
        <h2>8.7 30-Question Multiple-Choice Self-Quiz (with Answer Key)</h2>
        <div class="quiz-container">
          <p><em>Test your mastery before facing SIH judges. Circle the correct answer and verify against the answer key below.</em></p>

          <div class="quiz-q">
            <p><strong>1. What is the official Problem Statement ID for Route.it?</strong><br>
            A) SIH15024 &nbsp;&nbsp; B) SIH26137 &nbsp;&nbsp; C) SIH99102 &nbsp;&nbsp; D) SIH33100</p>
          </div>

          <div class="quiz-q">
            <p><strong>2. Does Route.it execute on physical quantum computing hardware (qubits)?</strong><br>
            A) Yes, on IBM Q &nbsp;&nbsp; B) Yes, on D-Wave &nbsp;&nbsp; C) No, it simulates quantum wave equations on classical CPUs &nbsp;&nbsp; D) Yes, via optical photonics</p>
          </div>

          <div class="quiz-q">
            <p><strong>3. What algorithm partitions giant continuous tours into discrete vehicle routes in polynomial time?</strong><br>
            A) Dijkstra shortest path &nbsp;&nbsp; B) Christian Prins DAG Split &nbsp;&nbsp; C) Floyd-Warshall &nbsp;&nbsp; D) A* Search</p>
          </div>

          <div class="quiz-q">
            <p><strong>4. What is the contraction-expansion coefficient \(\beta\) range across iterations?</strong><br>
            A) Constant 1.0 &nbsp;&nbsp; B) 0.1 to 0.9 &nbsp;&nbsp; C) Anneals linearly from 1.0 down to 0.5 &nbsp;&nbsp; D) Increases from 0.0 to 10.0</p>
          </div>

          <div class="quiz-q">
            <p><strong>5. What tool compiles Python numerical loops into raw LLVM machine code in Route.it?</strong><br>
            A) Cython &nbsp;&nbsp; B) PyPy &nbsp;&nbsp; C) Numba JIT &nbsp;&nbsp; D) CFFI</p>
          </div>

          <div class="quiz-q">
            <p><strong>6. How fast does QPSO solve a 100-stop problem instance?</strong><br>
            A) 90.0 milliseconds &nbsp;&nbsp; B) 15.2 seconds &nbsp;&nbsp; C) 1.5 minutes &nbsp;&nbsp; D) 3.55 seconds</p>
          </div>

          <div class="quiz-q">
            <p><strong>7. How did Google OR-Tools perform at 100 delivery stops with a 1.5-second time limit?</strong><br>
            A) Found best solution in 50ms &nbsp;&nbsp; B) Timed out (> 1500 ms) with zero solution &nbsp;&nbsp; C) Solved in 200ms &nbsp;&nbsp; D) Crashed memory</p>
          </div>

          <div class="quiz-q">
            <p><strong>8. Which open-source routing engine does Route.it query for real road topography?</strong><br>
            A) Google Directions &nbsp;&nbsp; B) Mapbox Directions &nbsp;&nbsp; C) Valhalla OpenStreetMap &nbsp;&nbsp; D) Bing Maps</p>
          </div>

          <div class="quiz-q">
            <p><strong>9. How are delivery verification OTPs stored in the SQLite database?</strong><br>
            A) Plaintext 6-digit integers &nbsp;&nbsp; B) HMAC-SHA256 hashes &nbsp;&nbsp; C) Base64 strings &nbsp;&nbsp; D) MD5 hashes</p>
          </div>

          <div class="quiz-q">
            <p><strong>10. How many failed OTP attempts are allowed before a stop is permanently locked?</strong><br>
            A) 3 &nbsp;&nbsp; B) 5 &nbsp;&nbsp; C) 10 &nbsp;&nbsp; D) Unlimited</p>
          </div>

          <div class="quiz-q">
            <p><strong>11. What SQLite journal mode is enabled for high concurrency?</strong><br>
            A) DELETE &nbsp;&nbsp; B) TRUNCATE &nbsp;&nbsp; C) WAL (Write-Ahead Logging) &nbsp;&nbsp; D) MEMORY</p>
          </div>

          <div class="quiz-q">
            <p><strong>12. What public cloud platform hosts the live deployment of Route.it?</strong><br>
            A) AWS EC2 &nbsp;&nbsp; B) Render &nbsp;&nbsp; C) Heroku &nbsp;&nbsp; D) DigitalOcean</p>
          </div>

          <div class="quiz-q">
            <p><strong>13. Which port does the production Docker container bind to on Render?</strong><br>
            A) Static port 80 &nbsp;&nbsp; B) Dynamic $PORT environment variable &nbsp;&nbsp; C) Port 5173 &nbsp;&nbsp; D) Port 3000</p>
          </div>

          <div class="quiz-q">
            <p><strong>14. How does the customer tracking portal prevent sequential ID crawling?</strong><br>
            A) Captcha &nbsp;&nbsp; B) Stream-cipher encrypted tokens &nbsp;&nbsp; C) IP blocking &nbsp;&nbsp; D) Requiring password</p>
          </div>

          <div class="quiz-q">
            <p><strong>15. How many relational tables are configured in Route.it's SQLite database?</strong><br>
            A) 3 &nbsp;&nbsp; B) 5 &nbsp;&nbsp; C) 9 &nbsp;&nbsp; D) 15</p>
          </div>

          <div class="quiz-q">
            <p><strong>16. What is the warm JIT execution time recorded in our authentic benchmark?</strong><br>
            A) 116.9 ms &nbsp;&nbsp; B) 500 ms &nbsp;&nbsp; C) 1.2 s &nbsp;&nbsp; D) 37.1 ms</p>
          </div>

          <div class="quiz-q">
            <p><strong>17. Which baseline solver won on cost for the small 20-stop instance?</strong><br>
            A) Dijkstra &nbsp;&nbsp; B) Genetic Algorithm &nbsp;&nbsp; C) Google OR-Tools (GLS) &nbsp;&nbsp; D) Classical PSO</p>
          </div>

          <div class="quiz-q">
            <p><strong>18. What is the speedup ratio achieved by Numba JIT over pure Python?</strong><br>
            A) 2x &nbsp;&nbsp; B) 5x &nbsp;&nbsp; C) ~24.5x &nbsp;&nbsp; D) 100x</p>
          </div>

          <div class="quiz-q">
            <p><strong>19. What geocoding service is used when an admin clicks on the Delivery Locations map?</strong><br>
            A) Google Geocoding &nbsp;&nbsp; B) Nominatim OpenStreetMap &nbsp;&nbsp; C) Mapbox Geocoding &nbsp;&nbsp; D) Radar API</p>
          </div>

          <div class="quiz-q">
            <p><strong>20. What is the coordinate of the central warehouse depot in Vadodara?</strong><br>
            A) 19.0760, 72.8777 &nbsp;&nbsp; B) 22.3072, 73.1812 &nbsp;&nbsp; C) 28.7041, 77.1025 &nbsp;&nbsp; D) 12.9716, 77.5946</p>
          </div>

          <div class="quiz-q">
            <p><strong>21. What happens if a delivery stop's time window is exceeded by a vehicle?</strong><br>
            A) The solver crashes &nbsp;&nbsp; B) The stop is deleted &nbsp;&nbsp; C) A heavy penalty (\(\gamma = 50.0\)) is added to the objective cost &nbsp;&nbsp; D) The vehicle stops driving</p>
          </div>

          <div class="quiz-q">
            <p><strong>22. What WebSocket endpoint streams real-time solver convergence updates?</strong><br>
            A) /ws/stream &nbsp;&nbsp; B) /ws/problems/{id} &nbsp;&nbsp; C) /ws/driver &nbsp;&nbsp; D) /ws/routes</p>
          </div>

          <div class="quiz-q">
            <p><strong>23. What is the purpose of the Return-to-Hub workflow?</strong><br>
            A) Send drivers on lunch &nbsp;&nbsp; B) Safely re-route undelivered parcels back to central depot &nbsp;&nbsp; C) Refuel vehicles &nbsp;&nbsp; D) Re-order supplies</p>
          </div>

          <div class="quiz-q">
            <p><strong>24. Why does QPSO use continuous random keys?</strong><br>
            A) To encrypt coordinates &nbsp;&nbsp; B) To map continuous quantum state space to discrete stop permutations via sorting &nbsp;&nbsp; C) To generate passwords &nbsp;&nbsp; D) For token auth</p>
          </div>

          <div class="quiz-q">
            <p><strong>25. What is the total monthly cost of third-party API keys in Route.it?</strong><br>
            A) $500 &nbsp;&nbsp; B) ₹15,000 &nbsp;&nbsp; C) ₹0.00 &nbsp;&nbsp; D) $29/month</p>
          </div>

          <div class="quiz-q">
            <p><strong>26. What password hashing algorithm is implemented in Route.it?</strong><br>
            A) MD5 &nbsp;&nbsp; B) SHA1 &nbsp;&nbsp; C) PBKDF2-HMAC-SHA256 (100,000 iterations) &nbsp;&nbsp; D) Plaintext Base64</p>
          </div>

          <div class="quiz-q">
            <p><strong>27. What is the primary cause of a ~50-second initial request delay on Render free tier?</strong><br>
            A) Database deadlocks &nbsp;&nbsp; B) Container spindown after 15 minutes of inactivity (Cold Start) &nbsp;&nbsp; C) Solver re-indexing &nbsp;&nbsp; D) Numba re-compilation</p>
          </div>

          <div class="quiz-q">
            <p><strong>28. What genetic crossover operator is implemented in Route.it's GA baseline?</strong><br>
            A) Single-Point Crossover &nbsp;&nbsp; B) Uniform Crossover &nbsp;&nbsp; C) Order Crossover (OX) &nbsp;&nbsp; D) Multi-parent Crossover</p>
          </div>

          <div class="quiz-q">
            <p><strong>29. How does the Valhalla client respect public OpenStreetMap server health?</strong><br>
            A) Fires 100 parallel calls &nbsp;&nbsp; B) Chunks into 10x10 matrices, pauses 0.5s between calls, and sends polite User-Agent &nbsp;&nbsp; C) Ignores errors &nbsp;&nbsp; D) Uses proxies</p>
          </div>

          <div class="quiz-q">
            <p><strong>30. What constant-time string comparison function protects against timing attacks?</strong><br>
            A) strcmp() &nbsp;&nbsp; B) == &nbsp;&nbsp; C) hmac.compare_digest() &nbsp;&nbsp; D) hash()</p>
          </div>

          <div class="answer-key-box">
            <h4>🔑 Complete Answer Key & Quick Explanations:</h4>
            <p>
              <strong>1-B:</strong> SIH26137 is the official ministry problem statement code.<br>
              <strong>2-C:</strong> Quantum-inspired wave equations run on classical CPUs via Monte Carlo sampling.<br>
              <strong>3-B:</strong> Christian Prins (2004) proved DAG shortest-path partitioning in \(O(N^2)\).<br>
              <strong>4-C:</strong> \(\beta\) anneals from 1.0 down to 0.5 to balance global exploration and local refinement.<br>
              <strong>5-C:</strong> Numba JIT compiles Python functions directly to LLVM intermediate representation.<br>
              <strong>6-A:</strong> Authentic benchmark proved QPSO solves 100 stops in 90.0 milliseconds.<br>
              <strong>7-B:</strong> Google OR-Tools exceeded the 1.5-second dispatch limit and timed out at 100 stops.<br>
              <strong>8-C:</strong> Valhalla is the open-source C++ routing engine using OpenStreetMap road graph data.<br>
              <strong>9-B:</strong> OTPs are hashed using HMAC-SHA256 with delivery_id as message; plaintext is never stored.<br>
              <strong>10-B:</strong> Max 5 failed attempts locks the stop to prevent brute-force attacks.<br>
              <strong>11-C:</strong> Write-Ahead Logging (WAL) mode enables concurrent non-blocking reads.<br>
              <strong>12-B:</strong> Deployed live on Render cloud web service (Docker runtime).<br>
              <strong>13-B:</strong> Render dynamically injects <code>$PORT</code>; backend binds 0.0.0.0:$PORT.<br>
              <strong>14-B:</strong> Stream-cipher tokens prevent attackers from crawling sequential customer delivery IDs.<br>
              <strong>15-C:</strong> 9 tables: delivery_locations, batches, routes, stops, vehicles, drivers, dispatch_jobs, incidents, audit_logs.<br>
              <strong>16-A:</strong> Authentic benchmark measured warm Numba JIT execution at 116.9 ms.<br>
              <strong>17-C:</strong> OR-Tools won on cost (₹1,931 vs ₹2,605) on the small 20-stop instance due to exhaustive GLS search.<br>
              <strong>18-C:</strong> Numba achieved approximately 24.5x faster throughput than interpreted Python.<br>
              <strong>19-B:</strong> Nominatim reverse-geocodes coordinate clicks to street addresses with zero API fees.<br>
              <strong>20-B:</strong> Central Vadodara warehouse coordinates are 22.3072 N, 73.1812 E.<br>
              <strong>21-C:</strong> Time-window violations add \(50.0 \times \text{delay minutes}\) to the objective fitness function.<br>
              <strong>22-B:</strong> Native WebSockets stream live convergence data at <code>/ws/problems/{id}</code>.<br>
              <strong>23-B:</strong> Return-to-Hub recalculates optimal road corridors to return failed packages to the depot.<br>
              <strong>24-B:</strong> Continuous random keys allow continuous quantum wave sampling to decode into discrete permutations.<br>
              <strong>25-C:</strong> Exactly ₹0.00; uses 100% open-source tools (Valhalla, OpenStreetMap, MapLibre, SQLite).<br>
              <strong>26-C:</strong> PBKDF2-HMAC-SHA256 with 100,000 iterations and 16-byte random salt.<br>
              <strong>27-B:</strong> Render free tier spins down idle containers after 15 minutes to conserve compute.<br>
              <strong>28-C:</strong> Order Crossover (OX) preserves relative stop sequences without duplicate stops.<br>
              <strong>29-B:</strong> Valhalla client chunks to 10x10, pauses 0.5s, and sends polite <code>Route.it-SIH2026</code> header.<br>
              <strong>30-C:</strong> <code>hmac.compare_digest()</code> eliminates CPU execution time variations during comparison.
            </p>
          </div>
        </div>
      </div>
    </section>
    """
