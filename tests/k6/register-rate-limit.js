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


const EXISTING_EMAIL =
  __ENV.REGISTER_EMAIL;


const EXISTING_PHONE =
  __ENV.REGISTER_PHONE;


export default function () {

  const attempt =
    __ITER + 1;


  const response = http.post(
    `${BASE_URL}/api/auth/register`,

    JSON.stringify({
      full_name:
        "Rate Limit Test",

      email:
        EXISTING_EMAIL,

      phone:
        EXISTING_PHONE,

      password:
        "RateLimitTest123!",
    }),

    {
      headers: {
        "Content-Type":
          "application/json",
      },
    }
  );


  /*
   * Existing account:
   *
   * request 1-5 => 409 Duplicate
   * request 6   => 429 Rate Limit
   */

  const expectedStatus =
    attempt <= 5
      ? 409
      : 429;


  console.log(
    `Register ${attempt}` +
    ` | status=${response.status}` +
    ` | expected=${expectedStatus}`
  );


  check(
    response,
    {
      [`register ${attempt} => ${expectedStatus}`]:
        (res) =>
          res.status === expectedStatus,
    }
  );


  sleep(0.2);
}