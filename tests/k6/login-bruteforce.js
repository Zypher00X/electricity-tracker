import http from "k6/http";
import { check, sleep } from "k6";


export const options = {
  vus: 1,
  iterations: 6,

  thresholds: {
    checks: ["rate==1.0"],
  },
};


const BASE_URL =
  __ENV.BASE_URL ||
  "http://127.0.0.1:8000";


const IDENTIFIER =
  __ENV.TEST_IDENTIFIER ||
  "somchai@gmail.com";


export default function () {

  const payload = JSON.stringify({
    identifier: IDENTIFIER,

    // ตั้งใจให้ผิด
    password: "DefinitelyWrongPassword123!",
  });


  const response = http.post(
    `${BASE_URL}/api/auth/login`,
    payload,
    {
      headers: {
        "Content-Type":
          "application/json",
      },
    }
  );


  /*
   * LOGIN_FAILURE_RATE_LIMIT = 5
   *
   * ครั้ง 1-5 -> 401
   * ครั้ง 6   -> 429
   */

  const attempt =
    __ITER + 1;

  const expectedStatus =
    attempt <= 5
      ? 401
      : 429;


  console.log(
    `Attempt ${attempt}` +
    ` | status=${response.status}` +
    ` | expected=${expectedStatus}` +
    ` | retry-after=${response.headers["Retry-After"] || "-"}`
  );


  check(
    response,
    {
      [`attempt ${attempt} => ${expectedStatus}`]:
        (res) =>
          res.status === expectedStatus,
    }
  );


  sleep(0.2);
}