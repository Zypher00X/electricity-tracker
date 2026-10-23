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


const EMAIL =
  __ENV.TEST_EMAIL;


const PHONE =
  __ENV.TEST_PHONE;


export default function () {

  const attempt =
    __ITER + 1;


  /*
   * สลับ email กับ phone
   * แต่เป็น account เดียวกัน
   */

  const identifier =
    attempt % 2 === 1
      ? EMAIL
      : PHONE;


  const response = http.post(
    `${BASE_URL}/api/auth/login`,

    JSON.stringify({
      identifier:
        identifier,

      password:
        "WrongPassword123!",
    }),

    {
      headers: {
        "Content-Type":
          "application/json",
      },
    }
  );


  const expectedStatus =
    attempt <= 5
      ? 401
      : 429;


  console.log(
    `Attempt ${attempt}` +
    ` | identifier=${identifier}` +
    ` | status=${response.status}` +
    ` | expected=${expectedStatus}`
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