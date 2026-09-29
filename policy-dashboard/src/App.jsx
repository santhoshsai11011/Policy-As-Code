import { useEffect, useMemo, useState } from "react";
import { Pie } from "react-chartjs-2";
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from "chart.js";
import "./App.css";

ChartJS.register(ArcElement, Tooltip, Legend);

const API_BASE =
  import.meta.env.API_BASE_URL || "http://127.0.0.1:8001";

function App() {
  const [df, setDf] = useState([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("All");
  const [selectedId, setSelectedId] = useState(null);
  const [error, setError] = useState("");
  const [currentRun, setCurrentRun] = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  const [runs, setRuns] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [showDefinitions, setShowDefinitions] = useState(false);
  const [policyRules, setPolicyRules] = useState([]);

  useEffect(() => {
    loadData();
    loadRules();
  }, []);

  // ============================================================
  // LOAD POLICY RULES
  // ============================================================

  const loadRules = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/rules`);

      if (!response.ok) {
        throw new Error("Could not load policy rules");
      }

      const data = await response.json();

      setPolicyRules(
        Array.isArray(data)
          ? data
          : data.rules || []
      );
    } catch (err) {
      console.error("Failed to load policy rules:", err);
    }
  };

  // ============================================================
  // LOAD ALL RUNS
  // ============================================================

  const loadData = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/runs`);

      if (!response.ok) {
        throw new Error("Could not load evaluation history");
      }

      const runList = await response.json();

      setRuns(runList);

      if (runList.length === 0) {
        throw new Error(
          "No evaluation runs found in the database."
        );
      }

      await loadRun(runList[0].id);
    } catch (err) {
      setError(err.message);
    }
  };

  // ============================================================
  // LOAD SINGLE RUN
  // ============================================================

  const loadRun = async (runId) => {
    try {
      const response = await fetch(
        `${API_BASE}/api/runs/${runId}`
      );

      if (!response.ok) {
        throw new Error(
          "Could not load the selected evaluation run"
        );
      }

      const run = await response.json();

      setCurrentRun(run);
      setDf(run.records || []);

      setSearch("");
      setFilter("All");

      setSelectedId(
        run.records && run.records.length > 0
          ? run.records[0].record_id
          : null
      );

      setShowHistory(false);
      setError("");
    } catch (err) {
      setError(err.message);
    }
  };

  // ============================================================
  // OPEN HISTORY
  // ============================================================

  const openHistory = async () => {
    setShowHistory(true);
    setHistoryLoading(true);

    try {
      const response = await fetch(
        `${API_BASE}/api/runs`
      );

      if (!response.ok) {
        throw new Error(
          "Could not load evaluation history"
        );
      }

      setRuns(await response.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setHistoryLoading(false);
    }
  };

  // ============================================================
  // SUMMARY COUNTS
  // ============================================================

  const total = df.length;

  const passed = useMemo(
    () =>
      df.filter(
        (r) => r.outcome === "PASS"
      ).length,
    [df]
  );

  const flagged = useMemo(
    () =>
      df.filter(
        (r) => r.outcome === "FLAG"
      ).length,
    [df]
  );

  const blocked = useMemo(
    () =>
      df.filter(
        (r) => r.outcome === "BLOCK"
      ).length,
    [df]
  );

  const passRate = total
    ? ((passed / total) * 100).toFixed(1)
    : 0;

  // ============================================================
  // FILTER + SEARCH
  // ============================================================

  const filteredData = useMemo(() => {
    let data = [...df];

    if (filter !== "All") {
      data = data.filter(
        (r) => r.outcome === filter
      );
    }

    if (search.trim()) {
      const q = search.toLowerCase().trim();

      data = data.filter((row) =>
        String(row.record_id)
          .toLowerCase()
          .includes(q) ||
        String(row.outcome || "")
          .toLowerCase()
          .includes(q) ||
        JSON.stringify(
          row.triggered_rules || []
        )
          .toLowerCase()
          .includes(q)
      );
    }

    return data;
  }, [df, filter, search]);

  // ============================================================
  // SELECTED RECORD
  // ============================================================

  const selectedRecord = useMemo(
    () =>
      df.find(
        (record) =>
          String(record.record_id) ===
          String(selectedId)
      ),
    [df, selectedId]
  );

  // ============================================================
  // PIE CHART
  // ============================================================

  const pieData = {
    labels: ["PASS", "FLAG", "BLOCK"],
    datasets: [
      {
        data: [passed, flagged, blocked],
        backgroundColor: [
          "#22c55e",
          "#f59e0b",
          "#ef4444",
        ],
        borderWidth: 0,
      },
    ],
  };

  const pieOptions = {
    responsive: true,
    maintainAspectRatio: false,

    plugins: {
      legend: {
        position: "bottom",

        labels: {
          padding: 20,
        },
      },

      tooltip: {
        callbacks: {
          label: function (context) {
            const total =
              context.dataset.data.reduce(
                (sum, value) =>
                  sum + value,
                0
              );

            const percentage = total
              ? (
                  (context.raw / total) *
                  100
                ).toFixed(1)
              : 0;

            return `${context.label}: ${percentage}%`;
          },
        },
      },
    },
  };

  // ============================================================
  // OUTCOME HELPERS
  // ============================================================

  const getOutcomeClass = (outcome) => {
    if (outcome === "PASS") return "pass";
    if (outcome === "FLAG") return "flag";
    return "block";
  };

  const getIcon = (outcome) => {
    if (outcome === "PASS") return "✓";
    if (outcome === "FLAG") return "⚠";
    return "✕";
  };

  // ============================================================
  // INPUT FIELDS
  // ============================================================

  const inputFields = useMemo(() => {
    if (!selectedRecord) return [];

    return Object.keys(selectedRecord).filter(
      (field) =>
        ![
          "record_id",
          "outcome",
          "triggered_rules",
          "reason",
          "remediation",
        ].includes(field)
    );
  }, [selectedRecord]);

  // ============================================================
  // ERROR PAGE
  // ============================================================

  if (error) {
    return (
      <div className="error-page">
        <h2>Unable to load dashboard</h2>

        <p>{error}</p>

        <p>
          Make sure the FastAPI backend is running on
          <b> http://127.0.0.1:8001 </b>.
        </p>
      </div>
    );
  }

  // ============================================================
  // MAIN UI
  // ============================================================

  return (
    <div className="app">

      {/* ======================================================
          HEADER
      ====================================================== */}

      <header className="header">

        <div>

          <div className="breadcrumb">
            Evaluations / Run #
            {currentRun
              ? currentRun.run_number
              : "-"}
          </div>

          <h1>
            Policy Evaluation Results
          </h1>

          <p>
            {total} records evaluated ·{" "}
            {policyRules.length} policy rules loaded
          </p>

        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "12px",
          }}
        >

          {/* DEFINITIONS */}

          <button
            type="button"
            onClick={() =>
              setShowDefinitions(true)
            }
            style={{
              background: "#ffffff",
              border: "1px solid #dbe2ea",
              borderRadius: "12px",
              padding: "14px 18px",
              minWidth: "120px",
              cursor: "pointer",
              boxShadow:
                "0 2px 8px rgba(15, 23, 42, 0.05)",
              fontSize: "13px",
              fontWeight: "600",
              color: "#1e3a5f",
            }}
          >
            DEFINITIONS
          </button>

          {/* HISTORY */}

          <button
            type="button"
            onClick={openHistory}
            style={{
              background: "#ffffff",
              border: "1px solid #dbe2ea",
              borderRadius: "12px",
              padding: "14px 18px",
              minWidth: "150px",
              cursor: "pointer",
              boxShadow:
                "0 2px 8px rgba(15, 23, 42, 0.05)",
              fontSize: "13px",
              fontWeight: "600",
              color: "#1e3a5f",
            }}
          >
            EVALUATION HISTORY
          </button>

          {/* RUN DATE */}

          <div className="run-info">

            <span>
              RUN DATE & TIME
            </span>

            <strong>
              {currentRun
                ? `${new Date(
                    currentRun.run_date
                  ).toLocaleDateString()} ${new Date(
                    currentRun.run_date
                  ).toLocaleTimeString()}`
                : "-"}
            </strong>

          </div>

        </div>

      </header>

      {/* ======================================================
          HISTORY MODAL
      ====================================================== */}

      {showHistory && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background:
              "rgba(15, 23, 42, 0.35)",
            zIndex: 1000,
            display: "flex",
            justifyContent: "flex-end",
          }}
          onClick={() =>
            setShowHistory(false)
          }
        >

          <div
            style={{
              width: "min(760px, 92vw)",
              height: "100%",
              background: "#ffffff",
              padding: "28px",
              overflowY: "auto",
              boxShadow:
                "-8px 0 30px rgba(15, 23, 42, 0.15)",
            }}
            onClick={(e) =>
              e.stopPropagation()
            }
          >

            <div
              style={{
                display: "flex",
                justifyContent:
                  "space-between",
                alignItems: "center",
                marginBottom: "24px",
              }}
            >

              <div>

                <div
                  style={{
                    fontSize: "12px",
                    color: "#7c8da6",
                    letterSpacing:
                      "0.08em",
                    marginBottom: "6px",
                  }}
                >
                  DATABASE
                </div>

                <h2 style={{ margin: 0 }}>
                  Evaluation History
                </h2>

              </div>

              <button
                type="button"
                onClick={() =>
                  setShowHistory(false)
                }
                style={{
                  border:
                    "1px solid #dbe2ea",
                  background: "#ffffff",
                  borderRadius: "8px",
                  padding: "8px 12px",
                  cursor: "pointer",
                  fontSize: "18px",
                }}
                aria-label="Close evaluation history"
              >
                ×
              </button>

            </div>

            {historyLoading ? (
              <p>
                Loading evaluation history...
              </p>
            ) : runs.length === 0 ? (
              <p>
                No evaluation runs found.
              </p>
            ) : (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "10px",
                }}
              >

                {runs.map((run) => (

                  <button
                    key={run.id}
                    type="button"
                    onClick={() =>
                      loadRun(run.id)
                    }
                    style={{
                      width: "100%",
                      textAlign: "left",
                      border:
                        "1px solid #e1e7ef",
                      background:
                        currentRun &&
                        currentRun.id ===
                          run.id
                          ? "#f5f8fc"
                          : "#ffffff",
                      borderRadius: "10px",
                      padding: "16px",
                      cursor: "pointer",
                    }}
                  >

                    <div
                      style={{
                        display: "flex",
                        justifyContent:
                          "space-between",
                        alignItems: "center",
                        gap: "16px",
                      }}
                    >

                      <div>

                        <strong
                          style={{
                            fontSize: "16px",
                          }}
                        >
                          Run #{run.run_number}
                        </strong>

                        <div
                          style={{
                            marginTop: "5px",
                            fontSize: "13px",
                            color: "#718096",
                          }}
                        >
                          {new Date(
                            run.run_date
                          ).toLocaleDateString()}{" "}
                          {new Date(
                            run.run_date
                          ).toLocaleTimeString()}
                        </div>

                        <div
                          style={{
                            marginTop: "4px",
                            fontSize: "13px",
                            color: "#718096",
                          }}
                        >
                          {run.dataset_name} ·{" "}
                          {run.total_records} records
                        </div>

                      </div>

                      <div
                        style={{
                          display: "flex",
                          gap: "12px",
                          fontSize: "13px",
                          whiteSpace:
                            "nowrap",
                        }}
                      >
                        <span>
                          ✓ {run.pass_count}
                        </span>

                        <span>
                          ⚠ {run.flag_count}
                        </span>

                        <span>
                          ✕ {run.block_count}
                        </span>
                      </div>

                    </div>

                  </button>

                ))}

              </div>
            )}

          </div>

        </div>
      )}

      {/* ======================================================
          DEFINITIONS MODAL
      ====================================================== */}

      {showDefinitions && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background:
              "rgba(15, 23, 42, 0.35)",
            zIndex: 1100,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "24px",
          }}
          onClick={() =>
            setShowDefinitions(false)
          }
        >

          <div
            style={{
              width: "min(620px, 92vw)",
              background: "#ffffff",
              borderRadius: "16px",
              padding: "28px",
              boxShadow:
                "0 20px 50px rgba(15, 23, 42, 0.18)",
            }}
            onClick={(e) =>
              e.stopPropagation()
            }
          >

            <div
              style={{
                display: "flex",
                justifyContent:
                  "space-between",
                alignItems: "center",
                marginBottom: "24px",
              }}
            >

              <div>

                <div
                  style={{
                    fontSize: "12px",
                    color: "#7c8da6",
                    letterSpacing:
                      "0.08em",
                    marginBottom: "6px",
                  }}
                >
                  POLICY REFERENCE
                </div>

                <h2 style={{ margin: 0 }}>
                  Data Classification Definitions
                </h2>

              </div>

              <button
                type="button"
                onClick={() =>
                  setShowDefinitions(false)
                }
                style={{
                  border:
                    "1px solid #dbe2ea",
                  background: "#ffffff",
                  borderRadius: "8px",
                  padding: "8px 12px",
                  cursor: "pointer",
                  fontSize: "18px",
                }}
                aria-label="Close definitions"
              >
                ×
              </button>

            </div>

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "18px",
              }}
            >

              {["PII", "SPII", "CPII"].map(
                (category) => {

                  const rules =
                    policyRules.filter(
                      (rule) =>
                        rule.category ===
                        category
                    );

                  const title =
                    category === "PII"
                      ? "Personally Identifiable Information"
                      : category === "SPII"
                      ? "Sensitive Personally Identifiable Information"
                      : "Combination Personally Identifiable Information";

                  return (
                    <div key={category}>

                      <strong
                        style={{
                          fontSize: "16px",
                          color: "#1e3a5f",
                        }}
                      >
                        {category} — {title}
                      </strong>

                      <p
                        style={{
                          margin:
                            "7px 0 0",
                          color: "#5f6f85",
                          lineHeight: 1.6,
                        }}
                      >
                        {rules.length} rule
                        {rules.length === 1
                          ? ""
                          : "s"}{" "}
                        loaded from the
                        current policy.
                      </p>

                    </div>
                  );
                }
              )}

            </div>

          </div>

        </div>
      )}

      {/* ======================================================
          OVERVIEW
      ====================================================== */}

      <section className="overview">

        <div className="summary-section">

          <div className="summary-grid">

            <div className="summary-card pass-card">

              <span className="card-label">
                ✓ PASS
              </span>

              <strong>{passed}</strong>

              <small>
                {total
                  ? (
                      (passed / total) *
                      100
                    ).toFixed(1)
                  : 0}
                %
              </small>

            </div>

            <div className="summary-card flag-card">

              <span className="card-label">
                ⚠ FLAG
              </span>

              <strong>{flagged}</strong>

              <small>
                {total
                  ? (
                      (flagged / total) *
                      100
                    ).toFixed(1)
                  : 0}
                %
              </small>

            </div>

            <div className="summary-card block-card">

              <span className="card-label">
                ✕ BLOCK
              </span>

              <strong>{blocked}</strong>

              <small>
                {total
                  ? (
                      (blocked / total) *
                      100
                    ).toFixed(1)
                  : 0}
                %
              </small>

            </div>

            <div className="summary-card rate-card">

              <span className="card-label">
                ◔ PASS RATE
              </span>

              <strong>
                {passRate}%
              </strong>

              <small>
                {passed}/{total} passed
              </small>

            </div>

          </div>

        </div>

        <div className="chart-section">

          <h3>
            Outcome Distribution
          </h3>

          <div className="pie-container">

            <Pie
              data={pieData}
              options={pieOptions}
            />

          </div>

        </div>

      </section>

      {/* ======================================================
          MAIN CONTENT
      ====================================================== */}

      <section className="main-content">

        {/* ====================================================
            RECORDS PANEL
        ==================================================== */}

        <div className="records-panel">

          <div className="panel-header">

            <div>

              <h2>Records</h2>

              <span>
                {filteredData.length} records shown
              </span>

            </div>

          </div>

          <input
            className="search"
            placeholder="Search records..."
            value={search}
            onChange={(e) =>
              setSearch(e.target.value)
            }
          />

          <div className="filters">

            {[
              "All",
              "PASS",
              "FLAG",
              "BLOCK",
            ].map((name) => (

              <button
                key={name}
                className={`filter-button ${
                  filter === name
                    ? "active"
                    : ""
                }`}
                onClick={() =>
                  setFilter(name)
                }
              >

                {name === "PASS" && "✓ "}
                {name === "FLAG" && "⚠ "}
                {name === "BLOCK" && "✕ "}
                {name}

              </button>

            ))}

          </div>

          <div className="record-list">

            {filteredData.map((record) => {

              const outcome =
                record.outcome;

              const rules =
                record.triggered_rules
                  ?.length
                  ? record.triggered_rules
                      .map(
                        (rule) =>
                          rule.rule_id
                      )
                      .join(", ")
                  : "No violations";

              return (

                <button
                  key={record.record_id}
                  className={`record-item ${
                    String(selectedId) ===
                    String(record.record_id)
                      ? "selected"
                      : ""
                  }`}
                  onClick={() =>
                    setSelectedId(
                      record.record_id
                    )
                  }
                >

                  <span
                    className={`status-dot ${getOutcomeClass(
                      outcome
                    )}`}
                  >
                    {getIcon(outcome)}
                  </span>

                  <div className="record-info">

                    <strong>
                      REC-
                      {String(
                        record.record_id
                      ).padStart(4, "0")}
                    </strong>

                    <span>
                      {rules}
                    </span>

                  </div>

                  <span
                    className={`outcome-text ${getOutcomeClass(
                      outcome
                    )}`}
                  >
                    {outcome}
                  </span>

                </button>

              );
            })}

          </div>

        </div>

        {/* ====================================================
            ANALYSIS PANEL
        ==================================================== */}

        <div className="analysis-panel">

          {selectedRecord ? (
            <>

              {/* ANALYSIS HEADER */}

              <div className="analysis-header">

                <div>

                  <span className="analysis-label">
                    RECORD POLICY ANALYSIS
                  </span>

                  <h2>
                    REC-
                    {String(
                      selectedRecord.record_id
                    ).padStart(4, "0")}
                  </h2>

                </div>

                <span
                  className={`outcome-badge ${getOutcomeClass(
                    selectedRecord.outcome
                  )}`}
                >

                  {getIcon(
                    selectedRecord.outcome
                  )}{" "}

                  {selectedRecord.outcome}

                </span>

              </div>

              <div className="analysis-content">

                {/* ==================================================
                    POLICY RULES
                ================================================== */}

                <section className="analysis-section">

                  <h3>
                    Policy Rules
                  </h3>

                  {selectedRecord
                    .triggered_rules
                    ?.length > 0 ? (

                    <div className="rule-list">

                      {selectedRecord.triggered_rules.map(
                        (rule) => (

                          <div
                            className="rule-item"
                            key={rule.rule_id}
                          >

                            <strong>
                              {rule.rule_id}
                            </strong>

                            <span>
                              {rule.description}
                            </span>

                            <small
                              style={{
                                marginTop:
                                  "4px",
                                color:
                                  "#7c8da6",
                              }}
                            >
                              {rule.matched_fields
                                ?.join(
                                  " + "
                                )}{" "}
                              ·{" "}
                              {rule.outcome}
                            </small>

                          </div>

                        )
                      )}

                    </div>

                  ) : (

                    <div className="no-violations">
                      ✓ No policy violations detected
                    </div>

                  )}

                </section>

                {/* ==================================================
                    EXPLANATION
                ================================================== */}

                <section className="analysis-section">

                  <h3>
                    Explanation
                  </h3>

                  <div className="line-list">

                    {selectedRecord
                      .triggered_rules
                      ?.length > 0 ? (

                      selectedRecord.triggered_rules.map(
                        (rule) => (

                          <div
                            className="line-item"
                            key={rule.rule_id}
                          >

                            <span>
                              •
                            </span>

                            {rule.description}.

                          </div>

                        )
                      )

                    ) : (

                      <div className="line-item">

                        <span>
                          •
                        </span>

                        No PII, SPII or CPII detected.

                      </div>

                    )}

                  </div>

                </section>

                {/* ==================================================
                    INPUT DATA
                ================================================== */}

                <section className="analysis-section">

                  <h3>
                    Input Data
                  </h3>

                  <div className="input-grid">

                    {inputFields.map(
                      (field) => {

                        const value =
                          selectedRecord[
                            field
                          ];

                        if (
                          value ===
                            undefined ||
                          value === null ||
                          String(
                            value
                          ).trim() === ""
                        ) {
                          return null;
                        }

                        return (

                          <div
                            className="input-item"
                            key={field}
                          >

                            <span>
                              {field
                                .replaceAll(
                                  "_",
                                  " "
                                )
                                .replace(
                                  /\b\w/g,
                                  (l) =>
                                    l.toUpperCase()
                                )}
                            </span>

                            <strong>
                              {String(value)}
                            </strong>

                          </div>

                        );
                      }
                    )}

                  </div>

                </section>

                {/* ==================================================
                    SUGGESTED REMEDIATION
                ================================================== */}

                <section className="analysis-section">

                  <h3>
                    Suggested Remediation
                  </h3>

                  <div className="remediation-list">

                    <div className="remediation-item">

                      <span>
                        →
                      </span>

                      <span>
                        {selectedRecord.remediation ||
                          "No remediation required."}
                      </span>

                    </div>

                  </div>

                </section>

                {/* ==================================================
                    REASON
                ================================================== */}

                <section className="analysis-section">

                  <h3>
                    Decision Reason
                  </h3>

                  <div className="line-list">

                    <div className="line-item">

                      <span>
                        •
                      </span>

                      {selectedRecord.reason ||
                        "No policy rule was triggered."}

                    </div>

                  </div>

                </section>

              </div>

            </>

          ) : (

            <div className="empty-analysis">
              Select a record to view analysis
            </div>

          )}

        </div>

      </section>

    </div>
  );
}

export default App;