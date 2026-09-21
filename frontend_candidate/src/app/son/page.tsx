"use client";

import {
  useEffect,
  useMemo,
  useState,
} from "react";


const API_BASE =
  process.env
    .NEXT_PUBLIC_API_BASE_URL
  || "http://127.0.0.1:8000";


type ForecastRun = {
  run_id: string;
  forecast_rows: number;
  cells: number;
  horizon_steps: number;
  forecast_start: string | null;
  forecast_end: string | null;
};


type SonRules = {
  es_prb_threshold: number;
  es_max_active_users: number;
  es_min_steps: number;
  es_max_steps: number;

  mlb_prb_threshold: number;
  mlb_steps: number;

  cap_prb_threshold: number;
  cap_steps: number;
};


type Recommendation = {
  cell_name: string;

  recommendation:
    | "ES"
    | "MLB"
    | "CAP";

  module_label: string;
  triggering_condition: string;
  time_window: string;
  recommended_action: string;
  evidence: string;
};


type SonResult = {
  status: string;
  run_id: string;
  engine: string;

  total_cells: number;
  forecast_rows: number;
  horizon_steps: number;

  forecast_start: string;
  forecast_end: string;

  rules: SonRules;

  summary: {
    es: number;
    mlb: number;
    cap: number;
    recommendations: number;
    flagged_cells: number;
    no_action: number;
    overlapping_cells: number;
  };

  recommendations:
    Recommendation[];
};


type ModuleFilter =
  | "ALL"
  | "ES"
  | "MLB"
  | "CAP";


const DEFAULT_RULES:
  SonRules = {

  es_prb_threshold: 30,
  es_max_active_users: 10,
  // BAPS-SON-FINAL-POLISH-V1
  es_min_steps: 1,
  es_max_steps: 2,

  mlb_prb_threshold: 80,
  mlb_steps: 2,

  cap_prb_threshold: 80,
  cap_steps: 2,
};


type RangeControlProps = {
  label: string;
  value: number;
  min: number;
  max: number;
  suffix?: string;

  onChange:
    (
      value: number
    ) => void;
};


function RangeControl({
  label,
  value,
  min,
  max,
  suffix = "%",
  onChange,
}: RangeControlProps) {

  return (

    <div className="son-v2-control">

      <div className="son-v2-control-top">

        <span>
          {label}
        </span>

        <strong>
          {value}
          {suffix}
        </strong>

      </div>

      <input
        type="range"
        min={min}
        max={max}
        step={1}
        value={value}
        onChange={
          (
            event
          ) =>
            onChange(
              Number(
                event.target.value
              )
            )
        }
      />

      <div className="son-v2-range-minmax">
        <span>{min}</span>
        <span>{max}</span>
      </div>

    </div>
  );
}



function formatForecastBoundaryV6(value?: string | null) {
  if (!value) return "—";

  const dt = new Date(value);

  if (Number.isNaN(dt.getTime())) return value;

  const dd = String(dt.getDate()).padStart(2, "0");
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const yyyy = dt.getFullYear();
  const hh = String(dt.getHours()).padStart(2, "0");
  const mi = String(dt.getMinutes()).padStart(2, "0");

  return `${dd}.${mm}.${yyyy} ${hh}:${mi}`;
}

function getForecastEndV6(value?: string | null, resolutionMinutes = 15) {
  if (!value) return "—";

  const dt = new Date(value);

  if (Number.isNaN(dt.getTime())) return value;

  dt.setMinutes(dt.getMinutes() + resolutionMinutes);

  const dd = String(dt.getDate()).padStart(2, "0");
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const yyyy = dt.getFullYear();
  const hh = String(dt.getHours()).padStart(2, "0");
  const mi = String(dt.getMinutes()).padStart(2, "0");

  return `${dd}.${mm}.${yyyy} ${hh}:${mi}`;
}

const formatForecastTime =
  (
    value:
      string
      | null
      | undefined
  ) => {

    if (!value) {
      return "—";
    }

    const clean =
      value.replace(
        "T",
        " "
      );

    const parts =
      clean.split(
        " "
      );

    const date =
      parts[0];

    const time =
      parts[1]
        ?.slice(
          0,
          5
        )
      || "";

    const dateParts =
      date.split(
        "-"
      );

    if (
      dateParts.length
      !== 3
    ) {
      return clean;
    }

    return (
      `${dateParts[2]}.`
      + `${dateParts[1]}.`
      + `${dateParts[0]} `
      + time
    );
  };


export default function SonPage() {

  const [
    runs,
    setRuns,
  ] = useState<
    ForecastRun[]
  >([]);

  const [
    runId,
    setRunId,
  ] = useState("");


  // BAPS-SON-ACTIVE-SESSION-V1
  const [
    activeForecastSource,
    setActiveForecastSource,
  ] = useState(
    "Active Forecast"
  );

  const [
    rules,
    setRules,
  ] = useState<
    SonRules
  >(
    DEFAULT_RULES
  );

  const [
    result,
    setResult,
  ] = useState<
    SonResult | null
  >(null);

  const [
    running,
    setRunning,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState<
    string | null
  >(null);

  const [
    moduleFilter,
    setModuleFilter,
  ] = useState<
    ModuleFilter
  >("ALL");

  const [
    search,
    setSearch,
  ] = useState("");

  const [
    page,
    setPage,
  ] = useState(1);

  const pageSize = 6;


  useEffect(
    () => {

      const loadRuns =
        async () => {

          try {

            const response =
              await fetch(
                `${API_BASE}/son/runs`
              );

            const data =
              await response.json();

            if (!response.ok) {

              throw new Error(
                data?.detail
                || "Unable to load forecast runs."
              );
            }

            const loadedRuns:
              ForecastRun[] =
                data.runs
                || [];


            // BAPS-SON-ACTIVE-FORECAST-FIX-V3-1
            let activeRunId =
              "";

            let sourceLabel =
              "Active Forecast";


            try {

              const storedRunId =
                sessionStorage.getItem(
                  "baps_active_forecast_run_id"
                )
                ?? "";


              const forecastRaw =
                sessionStorage.getItem(
                  "baps_active_forecast_session"
                );


              let sessionRunId =
                "";


              if (
                forecastRaw
              ) {

                const forecastSession =
                  JSON.parse(
                    forecastRaw
                  ) as {
                    inputMode?:
                      "upload"
                      | "generate";

                    result?: {
                      run_id?: string;
                    } | null;
                  };


                sessionRunId =
                  forecastSession
                    .result
                    ?.run_id
                  ?? "";


                sourceLabel =
                  forecastSession
                    .inputMode ===
                    "generate"
                    ? "Generated Dataset"
                    : "Uploaded Dataset";
              }


              /*
              Primary reference:
                baps_active_forecast_run_id

              Fallback:
                baps_active_forecast_session.result.run_id
              */
              activeRunId =
                storedRunId
                || sessionRunId;


              /*
              Repair the short key when the full
              Forecast session is still available.
              */
              if (
                activeRunId
                && !storedRunId
              ) {

                sessionStorage.setItem(
                  "baps_active_forecast_run_id",
                  activeRunId
                );
              }

            } catch {
              // Session storage is optional.
            }


            const activeRun =
              loadedRuns.find(
                (
                  run
                ) =>
                  run.run_id ===
                  activeRunId
              )
              ?? null;


            if (
              activeRun
            ) {

              /*
              SON intentionally exposes only
              the current Active Forecast.
              Historical forecast runs remain
              stored by the backend but cannot
              be selected here.
              */
              setRuns(
                [
                  activeRun
                ]
              );

              setRunId(
                activeRun.run_id
              );

              setActiveForecastSource(
                sourceLabel
              );


              try {

                const sonRaw =
                  sessionStorage.getItem(
                    "baps_active_son_session"
                  );


                let restored =
                  false;


                if (
                  sonRaw
                ) {

                  const sonSession =
                    JSON.parse(
                      sonRaw
                    ) as {
                      version?: number;
                      runId: string;
                      rules:
                        SonRules;
                      result:
                        SonResult | null;
                    };


                  /*
                  Only restore the new schema.
                  Older SON sessions may contain
                  the obsolete 1-step defaults.
                  */
                  if (
                    sonSession.version === 4
                    &&
                    sonSession.runId ===
                    activeRun.run_id
                  ) {

                    if (
                      sonSession.rules
                    ) {

                      setRules(
                        sonSession.rules
                      );
                    }


                    if (
                      sonSession.result
                    ) {

                      setResult(
                        sonSession.result
                      );
                    }


                    restored =
                      true;
                  }
                }


                if (
                  !restored
                ) {

                  sessionStorage.removeItem(
                    "baps_active_son_session"
                  );


                  /*
                  Fresh defaults for the newly
                  connected Active Forecast.
                  */
                  const activeHorizon =
                    Math.max(
                      1,
                      activeRun.horizon_steps
                    );


                  setRules({
                    ...DEFAULT_RULES,

                    es_min_steps:
                      Math.min(
                        1,
                        activeHorizon
                      ),

                    es_max_steps:
                      Math.min(
                        2,
                        activeHorizon
                      ),

                    mlb_steps:
                      Math.min(
                        2,
                        activeHorizon
                      ),

                    cap_steps:
                      Math.min(
                        2,
                        activeHorizon
                      ),
                  });


                  setResult(
                    null
                  );
                }


                setError(
                  null
                );

              } catch {

                sessionStorage.removeItem(
                  "baps_active_son_session"
                );

                setResult(
                  null
                );
              }


            } else {

              setRuns(
                []
              );

              setRunId(
                ""
              );

              setResult(
                null
              );

              setActiveForecastSource(
                "No Active Forecast"
              );

              setError(
                "Run a Forecast before evaluating SON recommendations."
              );
            }

          } catch (
            err
          ) {

            setError(
              err instanceof Error
                ? err.message
                : "Unable to load forecast runs."
            );
          }
        };

      loadRuns();

    },
    []
  );


  const selectedRun =
    runs.find(
      (
        run
      ) =>
        run.run_id
        === runId
    ) ?? null;


  const horizonSteps =
    Math.max(
      1,
      selectedRun
        ?.horizon_steps
      || 1
    );


  // BAPS-SON-FINAL-POLISH-V2
  useEffect(
    () => {

      /*
      The page initially renders before the Active Forecast
      is loaded. At that moment horizonSteps is temporarily 1.

      Do not clamp SON defaults during that transient state,
      otherwise 2-step defaults permanently become 1 step.
      */
      if (
        !selectedRun
      ) {
        return;
      }


      setRules(
        (
          previous
        ) => ({
          ...previous,

          es_min_steps:
            Math.min(
              previous.es_min_steps,
              horizonSteps
            ),

          es_max_steps:
            Math.min(
              Math.max(
                previous.es_max_steps,
                Math.min(
                  previous.es_min_steps,
                  horizonSteps
                )
              ),
              horizonSteps
            ),

          mlb_steps:
            Math.min(
              previous.mlb_steps,
              horizonSteps
            ),

          cap_steps:
            Math.min(
              previous.cap_steps,
              horizonSteps
            ),
        })
      );

    },
    [
      selectedRun,
      horizonSteps
    ]
  );


  const updateRule =
    (
      key: keyof SonRules,
      value: number
    ) => {

      setRules(
        (
          previous
        ) => ({
          ...previous,
          [key]: value,
        })
      );

      setResult(
        null
      );


      try {

        sessionStorage.removeItem(
          "baps_active_son_session"
        );

      } catch {
        // Session storage is optional.
      }
    };


  const resetRules =
    () => {

      const maxStep =
        Math.max(
          1,
          horizonSteps
        );

      setRules({
        ...DEFAULT_RULES,

        es_min_steps:
          Math.min(
            1,
            maxStep
          ),

        es_max_steps:
          Math.min(
            2,
            maxStep
          ),

        mlb_steps:
          Math.min(
            2,
            maxStep
          ),

        cap_steps:
          Math.min(
            2,
            maxStep
          ),
      });

      setResult(
        null
      );

      setError(
        null
      );


      try {

        sessionStorage.removeItem(
          "baps_active_son_session"
        );

      } catch {
        // Session storage is optional.
      }
    };


  const evaluate =
    async () => {

      if (!runId) {
        return;
      }

      setRunning(
        true
      );

      setError(
        null
      );

      try {

        const response =
          await fetch(
            `${API_BASE}/son/evaluate`,
            {
              method: "POST",

              headers: {
                "Content-Type":
                  "application/json",
              },

              body:
                JSON.stringify(
                  {
                    run_id: runId,
                    rules,
                  }
                ),
            }
          );

        const data =
          await response.json();

        if (!response.ok) {

          throw new Error(
            data?.detail
            || "SON evaluation failed."
          );
        }

        setResult(
          data
        );


        try {

          sessionStorage.setItem(
            "baps_active_son_session",
            JSON.stringify(
              {
                version:
                  4,
                runId:
                  runId,
                rules:
                  rules,
                result:
                  data,
              }
            )
          );

        } catch {
          // Session storage is optional.
        }


        setModuleFilter(
          "ALL"
        );

        setSearch(
          ""
        );

        setPage(
          1
        );

      } catch (
        err
      ) {

        setError(
          err instanceof Error
            ? err.message
            : "SON evaluation failed."
        );

      } finally {

        setRunning(
          false
        );
      }
    };


  const filtered =
    useMemo(
      () => {

        if (!result) {
          return [];
        }

        const query =
          search
            .trim()
            .toLowerCase();

        return (
          result
            .recommendations
            .filter(
              (
                item
              ) => {

                const moduleMatch =
                  moduleFilter
                  === "ALL"
                  || item.recommendation
                    === moduleFilter;

                const searchable =
                  [
                    item.cell_name,
                    item.module_label,
                    item.triggering_condition,
                    item.time_window,
                    item.recommended_action,
                    item.evidence,
                  ]
                  .join(" ")
                  .toLowerCase();

                const searchMatch =
                  !query
                  || searchable.includes(
                    query
                  );

                return (
                  moduleMatch
                  && searchMatch
                );
              }
            )
        );

      },
      [
        result,
        moduleFilter,
        search,
      ]
    );


  useEffect(
    () => {
      setPage(
        1
      );
    },
    [
      moduleFilter,
      search,
    ]
  );


  const totalPages =
    Math.max(
      1,
      Math.ceil(
        filtered.length
        / pageSize
      )
    );


  const safePage =
    Math.min(
      page,
      totalPages
    );


  const pageRows =
    filtered.slice(
      (
        safePage - 1
      )
      * pageSize,

      safePage
      * pageSize
    );


  const recommendationTotal =
    result
      ?.summary
      .recommendations
    || 0;


  const esPct =
    recommendationTotal
      ? (
          (
            result?.summary.es
            || 0
          )
          / recommendationTotal
          * 100
        )
      : 0;


  const mlbPct =
    recommendationTotal
      ? (
          (
            result?.summary.mlb
            || 0
          )
          / recommendationTotal
          * 100
        )
      : 0;


  const donutBackground =
    recommendationTotal
      ? `conic-gradient(
          #23db9b 0 ${esPct}%,
          #986eff ${esPct}% ${esPct + mlbPct}%,
          #20bdf5 ${esPct + mlbPct}% 100%
        )`
      : "#12334a";


  const flaggedPct =
    result
      && result.total_cells
      ? (
          result.summary
            .flagged_cells
          / result.total_cells
          * 100
        )
      : 0;


  const noActionPct =
    result
      && result.total_cells
      ? (
          result.summary
            .no_action
          / result.total_cells
          * 100
        )
      : 0;


  const formatNumber =
    (
      value:
        number
        | null
        | undefined
    ) => {

      if (
        value === null
        || value === undefined
      ) {
        return "—";
      }

      return Number(
        value
      ).toLocaleString();
    };


  const exportCsv =
    () => {

      if (
        !result
        || result
          .recommendations
          .length === 0
      ) {
        return;
      }

      const header = [
        "CELL_NAME",
        "SON_MODULE",
        "TRIGGERING_CONDITION",
        "FORECAST_EVIDENCE",
        "TIME_WINDOW",
        "RECOMMENDED_ACTION",
      ];

      const escape =
        (
          value: unknown
        ) =>
          `"${String(
            value ?? ""
          ).replace(
            /"/g,
            '""'
          )}"`;

      const rows =
        result
          .recommendations
          .map(
            (
              item
            ) =>
              [
                item.cell_name,
                item.module_label,
                item.triggering_condition,
                item.evidence,
                item.time_window,
                item.recommended_action,
              ]
              .map(
                escape
              )
              .join(",")
          );

      const csv =
        [
          header.join(","),
          ...rows,
        ]
        .join("\n");

      const blob =
        new Blob(
          [
            csv
          ],
          {
            type:
              "text/csv;charset=utf-8;",
          }
        );

      const url =
        URL.createObjectURL(
          blob
        );

      const anchor =
        document.createElement(
          "a"
        );

      anchor.href =
        url;

      anchor.download =
        `${result.run_id}_son_recommendations.csv`;

      anchor.click();

      URL.revokeObjectURL(
        url
      );
    };


  return (

    <main className="son-v2-page">

      <section className="son-v2-hero">

        <div>

          <div className="son-v2-eyebrow">
            AI-POWERED · DATA-DRIVEN · HIGHER NETWORK PERFORMANCE
          </div>

          <h1>
            SON Recommendations
          </h1>

          <p>
            Convert forecasted conditions
            into proactive network actions.
          </p>

        </div>

        <div className="son-v2-hero-note">
          Smarter Networks.
          <br />
          Proactive Actions.
        </div>

      </section>


      <div className="son-v2-layout">

        <div className="son-v2-main-column">

          <section className="son-v2-panel">

            <div className="son-v2-panel-header">

              <div>

                <h2>
                  SON Rule Configuration
                </h2>

                <p>
                  Legacy SON decision rules,
                  now applied directly to the
                  selected forecast run.
                </p>

              </div>


              <div className="son-v2-header-actions">

                <button
                  className="son-v2-reset"
                  onClick={
                    resetRules
                  }
                >
                  Reset to Default
                </button>

                <button
                  className="son-v2-evaluate"
                  disabled={
                    !runId
                    || running
                  }
                  onClick={
                    evaluate
                  }
                >

                  {running
                    ? "Evaluating..."
                    : "Evaluate SON Rules"}

                </button>

              </div>

            </div>


            <div className="son-v2-active-forecast-strip">

              <div className="son-v2-active-forecast-main">

                <span>
                  Active Forecast
                </span>

                <strong>
                  {selectedRun
                    ? activeForecastSource
                    : "No Active Forecast"}
                </strong>

                <small>
                  {selectedRun
                    ? "Automatically linked from Forecast"
                    : "Complete a Forecast first"}
                </small>

              </div>


              <div className="son-v2-run-stat">

                <span>
                  Cells
                </span>

                <strong>
                  {formatNumber(
                    selectedRun
                      ?.cells
                  )}
                </strong>

              </div>


              <div className="son-v2-run-stat">

                <span>
                  Horizon
                </span>

                <strong>
                  {selectedRun
                    ? `${selectedRun.horizon_steps} Steps`
                    : "—"}
                </strong>

              </div>


              <div className="son-v2-run-stat">

                <span>
                  Duration
                </span>

                <strong>
                  {selectedRun
                    ? `${
                        (
                          selectedRun
                            .horizon_steps
                          * 15
                          / 60
                        )
                      } Hours`
                    : "—"}
                </strong>

              </div>


              <div className="son-v2-run-stat">

                <span>
                  Forecast Rows
                </span>

                <strong>
                  {formatNumber(
                    selectedRun
                      ?.forecast_rows
                  )}
                </strong>

              </div>


              <div className="son-v2-run-stat son-v6-time-stat">

                <span>
                  Forecast Start
                </span>

                <strong>
                  {formatForecastTime(
                    selectedRun
                      ?.forecast_start
                  )}
                </strong>

              </div>


              <div className="son-v2-run-stat son-v6-time-stat">

                <span>
                  Forecast End
                </span>

                <strong>
                  {selectedRun
                    ? getForecastEndV6(
                        selectedRun
                          .forecast_end
                      )
                    : "—"}
                </strong>

              </div>

            </div>


            <div className="son-v2-rules-grid">

              <article className="son-v2-rule-card es">

                <div className="son-v2-rule-title">

                  <div className="son-v2-module-icon">
                    ES
                  </div>

                  <div>
                    <h3>
                      Energy Saving
                    </h3>

                    <p>
                      Detect consecutive
                      low-load periods.
                    </p>
                  </div>

                </div>


                <RangeControl
                  label="PRB Threshold"
                  value={
                    rules
                      .es_prb_threshold
                  }
                  min={10}
                  max={50}
                  onChange={
                    (
                      value
                    ) =>
                      updateRule(
                        "es_prb_threshold",
                        value
                      )
                  }
                />


                <RangeControl
                  label="Max Active Users"
                  value={
                    rules
                      .es_max_active_users
                  }
                  min={1}
                  max={30}
                  suffix=""
                  onChange={
                    (
                      value
                    ) =>
                      updateRule(
                        "es_max_active_users",
                        value
                      )
                  }
                />


                <div className="son-v3-duration">

                  <div className="son-v3-duration-title">
                    Consecutive Duration Window
                  </div>

                  <div className="son-v3-duration-row">

                    <label>
                      <span>
                        Min
                      </span>

                      <select
                        value={
                          rules
                            .es_min_steps
                        }
                        onChange={
                          (
                            event
                          ) => {

                            const value =
                              Number(
                                event.target.value
                              );

                            setRules(
                              (
                                previous
                              ) => ({
                                ...previous,
                                es_min_steps:
                                  value,
                                es_max_steps:
                                  Math.max(
                                    previous
                                      .es_max_steps,
                                    value
                                  ),
                              })
                            );

                            setResult(
                              null
                            );
                          }
                        }
                      >

                        {Array
                          .from(
                            {
                              length:
                                horizonSteps,
                            },
                            (
                              _,
                              index
                            ) =>
                              index + 1
                          )
                          .map(
                            (
                              step
                            ) => (

                              <option
                                key={
                                  step
                                }
                                value={
                                  step
                                }
                              >
                                {step} step
                              </option>

                            )
                          )}

                      </select>
                    </label>


                    <span className="son-v3-duration-arrow">
                      →
                    </span>


                    <label>
                      <span>
                        Max
                      </span>

                      <select
                        value={
                          rules
                            .es_max_steps
                        }
                        onChange={
                          (
                            event
                          ) => {

                            const value =
                              Number(
                                event.target.value
                              );

                            setRules(
                              (
                                previous
                              ) => ({
                                ...previous,
                                es_max_steps:
                                  value,
                                es_min_steps:
                                  Math.min(
                                    previous
                                      .es_min_steps,
                                    value
                                  ),
                              })
                            );

                            setResult(
                              null
                            );
                          }
                        }
                      >

                        {Array
                          .from(
                            {
                              length:
                                horizonSteps,
                            },
                            (
                              _,
                              index
                            ) =>
                              index + 1
                          )
                          .map(
                            (
                              step
                            ) => (

                              <option
                                key={
                                  step
                                }
                                value={
                                  step
                                }
                              >
                                {step} step
                              </option>

                            )
                          )}

                      </select>
                    </label>

                  </div>

                </div>

              </article>


              <article className="son-v2-rule-card mlb">

                <div className="son-v2-rule-title">

                  <div className="son-v2-module-icon">
                    MLB
                  </div>

                  <div>
                    <h3>
                      Mobility Load Balancing
                    </h3>

                    <p>
                      Detect persistent
                      end-of-horizon high load.
                    </p>
                  </div>

                </div>


                <RangeControl
                  label="High PRB Threshold"
                  value={
                    rules
                      .mlb_prb_threshold
                  }
                  min={60}
                  max={95}
                  onChange={
                    (
                      value
                    ) =>
                      updateRule(
                        "mlb_prb_threshold",
                        value
                      )
                  }
                />


                <div className="son-v3-duration">

                  <div className="son-v3-duration-title">
                    Final Forecast Window
                  </div>

                  <select
                    className="son-v3-full-select"
                    value={
                      rules.mlb_steps
                    }
                    onChange={
                      (
                        event
                      ) =>
                        updateRule(
                          "mlb_steps",
                          Number(
                            event.target.value
                          )
                        )
                    }
                  >

                    {Array
                      .from(
                        {
                          length:
                            horizonSteps,
                        },
                        (
                          _,
                          index
                        ) =>
                          index + 1
                      )
                      .map(
                        (
                          step
                        ) => (

                          <option
                            key={
                              step
                            }
                            value={
                              step
                            }
                          >
                            Last {step} step
                            {step > 1
                              ? "s"
                              : ""}
                          </option>

                        )
                      )}

                  </select>

                </div>



              </article>


              <article className="son-v2-rule-card cap">

                <div className="son-v2-rule-title">

                  <div className="son-v2-module-icon">
                    CAP
                  </div>

                  <div>
                    <h3>
                      Capacity Expansion
                    </h3>

                    <p>
                      Detect persistent
                      high-load conditions.
                    </p>
                  </div>

                </div>


                <RangeControl
                  label="High PRB Threshold"
                  value={
                    rules
                      .cap_prb_threshold
                  }
                  min={60}
                  max={95}
                  onChange={
                    (
                      value
                    ) =>
                      updateRule(
                        "cap_prb_threshold",
                        value
                      )
                  }
                />


                <div className="son-v3-duration">

                  <div className="son-v3-duration-title">
                    Final Forecast Window
                  </div>

                  <select
                    className="son-v3-full-select"
                    value={
                      rules.cap_steps
                    }
                    onChange={
                      (
                        event
                      ) =>
                        updateRule(
                          "cap_steps",
                          Number(
                            event.target.value
                          )
                        )
                    }
                  >

                    {Array
                      .from(
                        {
                          length:
                            horizonSteps,
                        },
                        (
                          _,
                          index
                        ) =>
                          index + 1
                      )
                      .map(
                        (
                          step
                        ) => (

                          <option
                            key={
                              step
                            }
                            value={
                              step
                            }
                          >
                            Last {step} step
                            {step > 1
                              ? "s"
                              : ""}
                          </option>

                        )
                      )}

                  </select>

                </div>



              </article>

            </div>


            {error && (

              <div className="son-v2-error">
                {error}
              </div>

            )}

          </section>


          

        </div>


        <aside className="son-v2-side-column">

          <section className="son-v2-panel son-v4-summary-combined">

            <div className="son-v2-side-title">

              <h2>
                Recommendation Summary
              </h2>

              <span>
                {selectedRun
                  ? `${selectedRun.horizon_steps} forecast steps`
                  : "Awaiting run"}
              </span>

            </div>


            <div className="son-v2-summary-grid">

              <button
                className="es"
                onClick={
                  () =>
                    setModuleFilter(
                      "ES"
                    )
                }
              >

                <span>
                  ES Eligible
                </span>

                <strong>
                  {formatNumber(
                    result?.summary.es
                  )}
                </strong>

              </button>


              <button
                className="mlb"
                onClick={
                  () =>
                    setModuleFilter(
                      "MLB"
                    )
                }
              >

                <span>
                  MLB Recommended
                </span>

                <strong>
                  {formatNumber(
                    result?.summary.mlb
                  )}
                </strong>

              </button>


              <button
                className="cap"
                onClick={
                  () =>
                    setModuleFilter(
                      "CAP"
                    )
                }
              >

                <span>
                  Capacity Expansion
                </span>

                <strong>
                  {formatNumber(
                    result?.summary.cap
                  )}
                </strong>

              </button>


              <button
                className="neutral"
                onClick={
                  () =>
                    setModuleFilter(
                      "ALL"
                    )
                }
              >

                <span>
                  No Action Cells
                </span>

                <strong>
                  {formatNumber(
                    result?.summary.no_action
                  )}
                </strong>

              </button>

            </div>


            <div className="son-v4-summary-divider">

              <span>
                Recommendation Breakdown
              </span>

            </div>


            <div className="son-v2-breakdown">

              <div
                className="son-v2-donut"
                style={{
                  background:
                    donutBackground,
                }}
              >

                <div>

                  <strong>
                    {formatNumber(
                      recommendationTotal
                    )}
                  </strong>

                  <span>
                    Recommendations
                  </span>

                </div>

              </div>


              <div className="son-v2-legend">

                <div>

                  <i className="es" />

                  <span>
                    Energy Saving
                  </span>

                  <strong>
                    {formatNumber(
                      result?.summary.es
                    )}
                  </strong>

                </div>


                <div>

                  <i className="mlb" />

                  <span>
                    Mobility Load Balancing
                  </span>

                  <strong>
                    {formatNumber(
                      result?.summary.mlb
                    )}
                  </strong>

                </div>


                <div>

                  <i className="cap" />

                  <span>
                    Capacity Expansion
                  </span>

                  <strong>
                    {formatNumber(
                      result?.summary.cap
                    )}
                  </strong>

                </div>

              </div>

            </div>

          </section>


          




        </aside>


<section className="son-v2-panel son-v2-table-panel">

            <div className="son-v2-table-toolbar">

              <div>

                <h2>
                  SON Recommendations
                  {result
                    ? ` (${result.summary.recommendations})`
                    : ""}
                </h2>

              </div>


              <div className="son-v2-table-actions">

                <input
                  type="text"
                  placeholder="Search cell, condition or action..."
                  value={
                    search
                  }
                  onChange={
                    (
                      event
                    ) =>
                      setSearch(
                        event.target.value
                      )
                  }
                />


                <select
                  value={
                    moduleFilter
                  }
                  onChange={
                    (
                      event
                    ) =>
                      setModuleFilter(
                        event.target.value as ModuleFilter
                      )
                  }
                >

                  <option value="ALL">
                    All Modules
                  </option>

                  <option value="ES">
                    ES
                  </option>

                  <option value="MLB">
                    MLB
                  </option>

                  <option value="CAP">
                    CAP
                  </option>

                </select>


                <button
                  onClick={
                    exportCsv
                  }
                  disabled={
                    !result
                    || result
                      .recommendations
                      .length === 0
                  }
                >
                  Export
                </button>

              </div>

            </div>


            {!result ? (

              <div className="son-v2-empty">
                Adjust thresholds and click
                Evaluate SON Rules.
              </div>

            ) : filtered.length === 0 ? (

              <div className="son-v2-empty">
                No recommendations match
                the current filter.
              </div>

            ) : (

              <>

                <div className="son-v2-table-wrap">

                  <table className="son-v2-table">

                    <thead>

                      <tr>
                        <th>Cell ID</th>
                        <th>SON Module</th>
                        <th>Triggering Condition</th>
                        <th>Forecast Evidence</th>
                        <th>Time Window</th>
                        <th>Recommendation Action</th>
                      </tr>

                    </thead>

                    <tbody>

                      {pageRows.map(
                        (
                          item,
                          index
                        ) => (

                          <tr
                            key={
                              `${item.cell_name}-${item.recommendation}-${index}`
                            }
                          >

                            <td>
                              <strong>
                                {item.cell_name}
                              </strong>
                            </td>

                            <td>

                              <span
                                className={
                                  `son-v2-module-badge ${item.recommendation.toLowerCase()}`
                                }
                              >
                                {item.recommendation}
                              </span>

                            </td>

                            <td>
                              {item.triggering_condition}
                            </td>

                            <td>
                              <div className="son-v3-evidence-text">
                                {item.evidence}
                              </div>
                            </td>

                            <td>
                              {item.time_window}
                            </td>

                            <td>
                              {item.recommended_action}
                            </td>

                          </tr>

                        )
                      )}

                    </tbody>

                  </table>

                </div>


                <div className="son-v2-pagination">

                  <span>
                    Showing{" "}
                    {(safePage - 1) * pageSize + 1}
                    {"–"}
                    {Math.min(
                      safePage * pageSize,
                      filtered.length
                    )}
                    {" of "}
                    {filtered.length}
                  </span>


                  <div>

                    <button
                      disabled={
                        safePage <= 1
                      }
                      onClick={
                        () =>
                          setPage(
                            (
                              current
                            ) =>
                              Math.max(
                                1,
                                current - 1
                              )
                          )
                      }
                    >
                      Previous
                    </button>

                    <strong>
                      {safePage} / {totalPages}
                    </strong>

                    <button
                      disabled={
                        safePage >= totalPages
                      }
                      onClick={
                        () =>
                          setPage(
                            (
                              current
                            ) =>
                              Math.min(
                                totalPages,
                                current + 1
                              )
                          )
                      }
                    >
                      Next
                    </button>

                  </div>

                </div>

              </>

            )}

          </section>

      </div>

    </main>
  );
}
