const SECRET_PROPERTY = 'HERMES_DRAFT_SECRET';
const FROM_NAME_PROPERTY = 'HERMES_DRAFT_FROM_NAME';
const MAX_PER_DAY_PROPERTY = 'HERMES_DRAFT_MAX_PER_DAY';
const WINDOW_SECONDS = 300;
const MAX_BODY_LENGTH = 12000;

function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents || '{}');
    validatePayload(payload);
    const draft = GmailApp.createDraft(payload.to, payload.subject, payload.body_text, {
      name: getOptionalProperty(FROM_NAME_PROPERTY, 'Merry'),
    });
    incrementDailyCounter();
    return jsonResponse({ ok: true, draft_id: draft.getId() });
  } catch (error) {
    return jsonResponse({ ok: false, error: String(error && error.message ? error.message : error) });
  }
}

function validatePayload(payload) {
  const required = ['timestamp', 'nonce', 'to', 'subject', 'body_text', 'body_sha256', 'signature'];
  required.forEach(function (key) {
    if (!payload[key]) {
      throw new Error('missing_' + key);
    }
  });
  if (String(payload.body_text).length > MAX_BODY_LENGTH) {
    throw new Error('body_too_large');
  }
  const nowSeconds = Math.floor(Date.now() / 1000);
  const timestamp = Number(payload.timestamp);
  if (!Number.isFinite(timestamp) || Math.abs(nowSeconds - timestamp) > WINDOW_SECONDS) {
    throw new Error('stale_timestamp');
  }
  enforceDailyLimit();
  const actualBodySha256 = hexDigest(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, payload.body_text));
  if (actualBodySha256 !== String(payload.body_sha256)) {
    throw new Error('body_digest_mismatch');
  }
  const signingPayload = [
    String(payload.timestamp),
    String(payload.nonce),
    String(payload.to),
    String(payload.subject),
    String(payload.body_sha256),
  ].join('\n');
  const expectedSignature = hexDigest(
    Utilities.computeHmacSha256Signature(signingPayload, getRequiredProperty(SECRET_PROPERTY))
  );
  if (!constantTimeEquals(expectedSignature, String(payload.signature))) {
    throw new Error('bad_signature');
  }
}

function enforceDailyLimit() {
  const maxPerDay = Number(getOptionalProperty(MAX_PER_DAY_PROPERTY, '50'));
  const properties = PropertiesService.getScriptProperties();
  const key = dailyCounterKey();
  const current = Number(properties.getProperty(key) || '0');
  if (current >= maxPerDay) {
    throw new Error('daily_limit_exceeded');
  }
}

function incrementDailyCounter() {
  const lock = LockService.getScriptLock();
  lock.waitLock(5000);
  try {
    const properties = PropertiesService.getScriptProperties();
    const key = dailyCounterKey();
    const current = Number(properties.getProperty(key) || '0');
    properties.setProperty(key, String(current + 1));
  } finally {
    lock.releaseLock();
  }
}

function dailyCounterKey() {
  return 'draft_count_' + Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyyMMdd');
}

function getRequiredProperty(key) {
  const value = PropertiesService.getScriptProperties().getProperty(key);
  if (!value) {
    throw new Error('missing_script_property_' + key);
  }
  return value;
}

function getOptionalProperty(key, fallback) {
  return PropertiesService.getScriptProperties().getProperty(key) || fallback;
}

function hexDigest(bytes) {
  return bytes
    .map(function (byte) {
      const unsigned = byte < 0 ? byte + 256 : byte;
      return ('0' + unsigned.toString(16)).slice(-2);
    })
    .join('');
}

function constantTimeEquals(left, right) {
  if (left.length !== right.length) {
    return false;
  }
  let diff = 0;
  for (let index = 0; index < left.length; index += 1) {
    diff |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return diff === 0;
}

function jsonResponse(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload)).setMimeType(ContentService.MimeType.JSON);
}
