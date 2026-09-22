export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

export const UPLOAD_PATH =
  /^validation-runs\/uploads\/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\/actual\.csv$/;

const CSV_TYPES = new Set([
  "",
  "text/csv",
  "application/csv",
  "application/vnd.ms-excel",
]);

export function validateCsvFile(file) {
  if (
    !file
    || typeof file.name !== "string"
    || !/\.csv$/i.test(file.name)
    || file.name.length > 255
    || /[\\/\x00-\x1f]/.test(file.name)
  ) {
    throw new Error(
      "Choose a CSV file with a valid .csv filename."
    );
  }

  if (!CSV_TYPES.has(file.type)) {
    throw new Error(
      "Only CSV content types are supported."
    );
  }

  if (
    !Number.isSafeInteger(file.size)
    || file.size <= 0
    || file.size > MAX_UPLOAD_BYTES
  ) {
    throw new Error(
      "CSV must be non-empty and no larger than 50 MiB."
    );
  }
}

export function uploadConstraints(
  pathname,
  clientPayload,
  multipart,
) {
  if (!UPLOAD_PATH.test(pathname) || !multipart) {
    throw new Error(
      "Invalid validation upload destination."
    );
  }

  const file = JSON.parse(
    clientPayload ?? "{}"
  );

  validateCsvFile(file);

  return {
    allowedContentTypes: ["text/csv"],
    maximumSizeInBytes: file.size,
    validUntil: Date.now() + 15 * 60 * 1000,
    addRandomSuffix: false,
    allowOverwrite: false,
  };
}
