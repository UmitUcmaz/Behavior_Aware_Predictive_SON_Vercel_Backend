"use client";

import {
  useEffect,
  useRef,
  useState,
} from "react";

import ValidationComparisonChart
  from "@/components/ValidationComparisonChart";


const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL
  ?? "http://127.0.0.1:8000";


type ForecastRun = {
  run_id: string;
  source_type: string;
  source_label: string;
  ground_truth_available: boolean;
  ground_truth_filename: string | null;
  horizon_steps: number | null;
  total_cells: number | null;
  forecast_rows: number | null;
};


type Metric = {
  kpi: string;
  source_column: string;
  forecast_column: string;
  actual_column: string;
  count: number;
  mae: number | null;
  rmse: number | null;
  mape: number | null;
  r2: number | null;
};


type ValidationResult = {
  status: string;
  validation_id: string;
  forecast_run_id: string;
  actual_filename: string;
  actual_source: string;
  actual_source_label: string;
  forecast_rows: number;
  actual_rows: number;
  matched_rows: number;
  unmatched_forecast_rows: number;
  forecast_cells: number;
  actual_cells: number;
  matched_cells: number;
  match_rate_percent: number;
  kpis: string[];
  cells: string[];
  metrics: Metric[];
  macro: {
    mape: number | null;
    r2: number | null;
  };
  download_url: string;
};


function numberFormat(
  value:
    number
    | null
    | undefined
) {

  if (
    value === null
    || value === undefined
  ) {
    return "—";
  }

  return new Intl.NumberFormat(
    "en-US"
  ).format(value);
}


function decimal(
  value:
    number
    | null
    | undefined,
  digits=3,
) {

  if (
    value === null
    || value === undefined
  ) {
    return "—";
  }

  return value.toFixed(
    digits
  );
}


function kpiLabel(
  kpi: string
) {

  if (
    kpi ===
    "UL_PRB_UTILIZATION"
  ) {
    return "UL PRB Utilization";
  }

  if (
    kpi ===
    "DL_PRB_UTILIZATION"
  ) {
    return "DL PRB Utilization";
  }

  if (
    kpi ===
    "ACTIVE_USERS"
  ) {
    return "Active Users";
  }

  return kpi;
}


function validationTimestamp(validationId: string) {
  const match = /^VAL-(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})\d*Z$/.exec(validationId);
  if (!match) return null;
  return `${match[1]}-${match[2]}-${match[3]}T${match[4]}:${match[5]}:${match[6]}Z`;
}

// BAPS-ACTIVE-SESSION-V1
export default function ValidationPage() {

  const inputRef =
    useRef<HTMLInputElement>(
      null
    );

  const [
    runs,
    setRuns,
  ] =
    useState<ForecastRun[]>(
      []
    );

  const [
    runId,
    setRunId,
  ] =
    useState("");

  const [
    actualFile,
    setActualFile,
  ] =
    useState<File | null>(
      null
    );

  const [
    running,
    setRunning,
  ] =
    useState(false);

  const [
    result,
    setResult,
  ] =
    useState<ValidationResult | null>(
      null
    );

  const [
    error,
    setError,
  ] =
    useState<string | null>(
      null
    );


  useEffect(() => {

    async function loadRuns() {

      try {

        const response =
          await fetch(
            `${API_BASE_URL}/validation/runs`,
            {
              cache:
                "no-store",
            }
          );

        if (!response.ok) {
          return;
        }

        const body =
          await response.json();

        const available =
          (
            body?.runs
            ?? []
          ) as ForecastRun[];

        // BAPS-VALIDATION-ACTIVE-FORECAST-ONLY-V1

        let activeForecastRunId =
          "";

        let savedValidation:
          {
            runId: string;
            result:
              ValidationResult | null;
          }
          | null =
            null;


        try {

          activeForecastRunId =
            sessionStorage.getItem(
              "baps_active_forecast_run_id"
            )
            ?? "";


          const validationRaw =
            sessionStorage.getItem(
              "baps_active_validation_session"
            );


          if (
            validationRaw
          ) {

            savedValidation =
              JSON.parse(
                validationRaw
              );
          }

        } catch {
          // Ignore invalid session data.
        }


        const activeRun =
          available.find(
            (
              run
            ) =>
              run.run_id ===
              activeForecastRunId
          )
          ?? null;


        /*
        Validation intentionally exposes only
        the user's current Active Forecast.

        Historical forecast runs remain stored
        by the backend but are not selectable
        here, preventing accidental validation
        against an older forecast.
        */
        if (
          activeRun
        ) {

          setRuns(
            [
              activeRun
            ]
          );

          setRunId(
            activeRun.run_id
          );


          if (
            savedValidation
              ?.result
              ?.forecast_run_id ===
              activeRun.run_id
          ) {

            setResult(
              savedValidation.result
            );

          } else {

            setResult(
              null
            );
          }

        } else {

          /*
          No active Forecast in this browser
          session. Do not silently select an
          older backend run.
          */
          setRuns(
            []
          );

          setRunId(
            ""
          );

          setResult(
            null
          );
        }


      } catch {
      }
    }

    void loadRuns();

  }, []);


  const selectedRun =
    runs.find(
      (
        run
      ) =>
        run.run_id ===
        runId
    ) ?? null;


  const automaticGroundTruth =
    Boolean(
      selectedRun
      ?.ground_truth_available
    );


  const runValidation =
    async () => {

      if (
        !runId
        || (
          !automaticGroundTruth
          && !actualFile
        )
      ) {
        return;
      }

      setRunning(true);
      setResult(null);
      setError(null);

      const formData =
        new FormData();

      formData.append(
        "run_id",
        runId
      );

      if (actualFile) {

        formData.append(
          "file",
          actualFile
        );
      }

      try {

        const response =
          await fetch(
            `${API_BASE_URL}/validate`,
            {
              method:
                "POST",
              body:
                formData,
            }
          );

        if (!response.ok) {

          let detail =
            `Validation failed (${response.status}).`;

          try {

            const body =
              await response.json();

            if (body?.detail) {
              detail =
                String(
                  body.detail
                );
            }

          } catch {
          }

          throw new Error(
            detail
          );
        }

        const body:
          ValidationResult =
            await response.json();

        setResult(
          body
        );


        try {

          sessionStorage.setItem(
            "baps_active_validation_session",
            JSON.stringify(
              {
                runId:
                  runId,
                result:
                  body,
              }
            )
          );

        } catch {
          // Session storage is optional.
        }

      } catch (
        validationError
      ) {

        setError(
          validationError
          instanceof Error
            ? validationError.message
            : "Validation failed."
        );

      } finally {
        setRunning(false);
      }
    };


  const reset = () => {

    setActualFile(null);
    setResult(null);
    setError(null);

    if (
      inputRef.current
    ) {
      inputRef.current.value =
        "";
    }


    try {

      sessionStorage.removeItem(
        "baps_active_validation_session"
      );

    } catch {
      // Session storage is optional.
    }
  };


  const completedAt = result ? validationTimestamp(result.validation_id) : null;

  return (
    <div className="validation-page">

      <section className="validation-banner">

        <img
          src="/images/home-v6-city-reference.png"
          alt=""
        />

        <div className="validation-banner-fade" />

        <div className="validation-banner-copy">

          <span>
            TEST & VALIDATION
          </span>

          <h1>
            Model Accuracy & Validation
          </h1>

          <p>
            Compare forecasts with actual network data and measure prediction accuracy.
          </p>

        </div>

      </section>


      <div className="validation-main-grid">


        <aside className="validation-sidebar">
          <section className="validation-config">

          <div className="validation-config-title">

            <span>
              ◈
            </span>

            <h2>
              Validation Configuration
            </h2>

            <button
              type="button"
              onClick={reset}
            >
              ↻ Reset
            </button>

          </div>


          {/* BAPS-VALIDATION-UNIFIED-SOURCE-V1 */}
          <div className="validation-step">

            <div className="validation-step-title">

              <b>
                1
              </b>

              <strong>
                Validation Data Source
              </strong>

            </div>


            <div className="validation-source-tabs">

              <button
                type="button"
                className={
                  automaticGroundTruth
                    ? "active"
                    : "disabled"
                }
                disabled={
                  !automaticGroundTruth
                }
              >

                <span>
                  ◈
                </span>

                <strong>
                  Generated Ground Truth
                </strong>

                <small>
                  {automaticGroundTruth
                    ? "Automatically linked"
                    : "Not available"}
                </small>

              </button>


              <button
                type="button"
                className={
                  !automaticGroundTruth
                    ? "active"
                    : "disabled"
                }
                disabled={
                  automaticGroundTruth
                }
                onClick={
                  () => {

                    if (
                      !automaticGroundTruth
                    ) {

                      inputRef.current
                        ?.click();
                    }
                  }
                }
              >

                <span>
                  ⇧
                </span>

                <strong>
                  Upload Actual Data
                </strong>

                <small>
                  {automaticGroundTruth
                    ? "Not required"
                    : actualFile
                      ? "Actual CSV selected"
                      : "CSV required"}
                </small>

              </button>

            </div>


            {selectedRun ? (

              <div className="validation-active-forecast-card">

                <div className="validation-active-forecast-head">

                  <span>
                    Active Forecast
                  </span>

                  <strong
                    className={
                      automaticGroundTruth
                        ? "available"
                        : "required"
                    }
                  >

                    {automaticGroundTruth
                      ? "Ground Truth Available ✓"
                      : "Actual Data Required"}

                  </strong>

                </div>


                <div className="validation-active-forecast-main">

                  <strong>

                    {selectedRun.source_type ===
                    "generated"
                      ? "Generated Dataset"
                      : "Uploaded Dataset"}

                  </strong>

                  <span>

                    {selectedRun.total_cells
                      ? `${selectedRun.total_cells.toLocaleString()} Cells`
                      : "Cells —"}

                    {" · "}

                    {selectedRun.horizon_steps
                      ? `${selectedRun.horizon_steps} Steps / ${
                          (
                            selectedRun.horizon_steps
                            * 15
                            / 60
                          )
                        } Hours`
                      : "Forecast Horizon —"}

                  </span>

                </div>


                <div className="validation-active-forecast-source">

                  <span>
                    Validation Source
                  </span>

                  <strong>

                    {automaticGroundTruth
                      ? "Generated Ground Truth"
                      : "Uploaded Actual Network Data"}

                  </strong>

                </div>

              </div>

            ) : (

              <div className="validation-active-forecast-empty">

                <strong>
                  No Active Forecast
                </strong>

                <span>
                  Run a Forecast before Validation.
                </span>

              </div>

            )}


            {!automaticGroundTruth && (

              <label className="validation-upload validation-upload-active">

                <input
                  ref={inputRef}
                  type="file"
                  accept=".csv,text/csv"
                  hidden
                  onChange={
                    (
                      event
                    ) => {

                      const file =
                        event.target
                          .files?.[0]
                        ?? null;

                      setActualFile(
                        file
                      );

                      setResult(null);
                      setError(null);
                    }
                  }
                />

                <span>
                  {actualFile
                    ? "✓"
                    : "⇧"}
                </span>

                <strong>

                  {actualFile
                    ? actualFile.name
                    : "Upload Actual CSV"}

                </strong>

                <small>

                  {actualFile
                    ? `${(
                        actualFile.size
                        / 1024
                        / 1024
                      ).toFixed(2)} MB · Ready for validation`
                    : "Select actual network data covering the forecast period"}

                </small>

              </label>

            )}

          </div>


          <button
            type="button"
            className="validation-run-button"
            disabled={
              !runId
              || (
                !automaticGroundTruth
                && !actualFile
              )
              || running
            }
            onClick={
              runValidation
            }
          >
            {running
              ? "◌ Running Validation..."
              : "▶ Run Validation"}
          </button>


          {error && (

            <div className="validation-error">
              <strong>
                Validation failed
              </strong>
              <span>
                {error}
              </span>
            </div>

          )}

        </section>
          <section className="validation-panel validation-status-compact">

              <div className="validation-section-title">
                <span>
                  ✓
                </span>
                <h2>
                  Validation Status
                </h2>
              </div>

              <div className="validation-status-content">

                <strong>
                  {running
                    ? "Processing"
                    : result
                      ? "Completed"
                      : "Ready"}
                </strong>
                {completedAt && !running && (
                  <time className="validation-completed-at" dateTime={completedAt}>
                    {new Date(completedAt).toLocaleString("en-US", {
                      month: "short", day: "numeric", year: "numeric",
                      hour: "numeric", minute: "2-digit",
                    })}
                  </time>
                )}

                <div>
                  <span>
                    Actual Rows
                  </span>
                  <b>
                    {numberFormat(
                      result?.actual_rows
                    )}
                  </b>
                </div>

                <div>
                  <span>
                    Unmatched Forecast
                  </span>
                  <b>
                    {numberFormat(
                      result?.unmatched_forecast_rows
                    )}
                  </b>
                </div>

                <div>
                  <span>
                    KPIs Evaluated
                  </span>
                  <b>
                    {numberFormat(
                      result?.kpis.length
                    )}
                  </b>
                </div>


                <div>
                  <span>
                    Actual Source
                  </span>
                  <b>
                    {result
                      ? result.actual_source_label
                      : automaticGroundTruth
                        ? "Generated Ground Truth"
                        : "Upload Required"}
                  </b>
                </div>

              </div>

            </section></aside>


        <main className="validation-content">


          <div className="validation-summary-row">

            <section className="validation-panel validation-combined-summary-panel">

              <div className="validation-summary-groups"><div className="validation-summary-group "><div className="validation-summary-group-title">
                  <span>
                    ▤
                  </span>
                  <h2>
                    Matching Summary
                  </h2>
                </div><div className="validation-summary-cards">

                  <div>
                    <small>
                      Forecast Rows
                    </small>
                    <strong>
                      {numberFormat(
                        result?.forecast_rows
                      )}
                    </strong>
                    <span>
                      Selected forecast output
                    </span>
                  </div>

                  <div>
                    <small>
                      Matched Rows
                    </small>
                    <strong>
                      {numberFormat(
                        result?.matched_rows
                      )}
                    </strong>
                    <span>
                      Forecast ↔ Actual
                    </span>
                  </div>

                  <div>
                    <small>
                      Matched Cells
                    </small>
                    <strong>
                      {numberFormat(
                        result?.matched_cells
                      )}
                    </strong>
                    <span>
                      Common cells
                    </span>
                  </div>

                  <div>
                    <small>
                      Match Rate
                    </small>
                    <strong>
                      {result
                        ? `${decimal(
                            result.match_rate_percent,
                            1
                          )}%`
                        : "—"}
                    </strong>
                    <span>
                      Forecast row coverage
                    </span>
                  </div>

                </div></div><div className="validation-summary-group validation-summary-group-accuracy"><div className="validation-summary-group-title validation-accuracy-group-title">
                  <span>
                    ◫
                  </span>
                  <h2>
                    Accuracy Summary
                  </h2>
                </div><div className="validation-accuracy-cards">

                  <div>
                    <small>
                      Macro MAPE
                    </small>
                    <strong>
                      {result
                        && result.macro.mape
                        !== null
                        ? `${decimal(
                            result.macro.mape,
                            2
                          )}%`
                        : "—"}
                    </strong>
                  </div>

                  <div>
                    <small>
                      Macro R²
                    </small>
                    <strong>
                      {decimal(
                        result?.macro.r2,
                        4
                      )}
                    </strong>
                  </div>

                  <div>
                    <small>
                      Validation Rows
                    </small>
                    <strong>
                      {numberFormat(
                        result?.matched_rows
                      )}
                    </strong>
                  </div>

                  <div>
                    <small>
                      KPI Count
                    </small>
                    <strong>
                      {numberFormat(
                        result?.kpis.length
                      )}
                    </strong>
                  </div>

                </div></div></div>

              <div className="validation-table">

                <div className="validation-table-head">
                  <span>KPI</span>
                  <span>Samples</span>
                  <span>MAE</span>
                  <span>RMSE</span>
                  <span>MAPE</span>
                  <span>R²</span>
                </div>

                {!result ? (

                  <div className="validation-table-empty">
                    Validation results will appear here.
                  </div>

                ) : (

                  result.metrics.map(
                    (
                      metric
                    ) => (
                      <div
                        key={
                          metric.kpi
                        }
                        className="validation-table-row"
                      >
                        <strong>
                          {kpiLabel(
                            metric.kpi
                          )}
                        </strong>

                        <span>
                          {numberFormat(
                            metric.count
                          )}
                        </span>

                        <span>
                          {decimal(
                            metric.mae,
                            4
                          )}
                        </span>

                        <span>
                          {decimal(
                            metric.rmse,
                            4
                          )}
                        </span>

                        <span>
                          {metric.mape
                            !== null
                            ? `${decimal(
                                metric.mape,
                                2
                              )}%`
                            : "—"}
                        </span>

                        <span>
                          {decimal(
                            metric.r2,
                            4
                          )}
                        </span>

                      </div>
                    )
                  )

                )}

              </div>

              <div className="validation-inline-export">
                <button
                  type="button"
                  disabled={!result}
                  onClick={
                    () => {

                      if (!result) {
                        return;
                      }

                      window.open(
                        `/api/validation-download?validation_id=${encodeURIComponent(result.validation_id)}`,
                        "_blank"
                      );
                    }
                  }
                >
                  ⇩ Export Validation CSV
                </button>
              </div>

            </section>

          </div>


          <ValidationComparisonChart
            apiBaseUrl={
              API_BASE_URL
            }
            validationId={
              result?.validation_id
              ?? null
            }
            cells={
              result?.cells
              ?? []
            }
            kpis={
              result?.kpis
              ?? []
            }
          />

        </main>

      </div>

    </div>
  );
}
