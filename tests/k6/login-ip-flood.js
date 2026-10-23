import http from "k6/http";
import { check } from "k6";


export const options = {
  vus: 1,
  iterations: 35,

  thresholds: {
    checks: ["rate==1.0"],
  },
};


const BASE_URL =
  __ENV.BASE_URL ||
  "http://127.0.0.1:8000";


export default function () {

  const attempt =
    __ITER + 1;


  /*
   * เปลี่ยน identifier ทุกครั้ง
   * เพื่อไม่ให้ IP+identifier limiter
   * ตัดเราก่อน
   */

  const identifier =
    `attack-${attempt}@example.invalid`;


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


  /*
   * LOGIN_IP_RATE_LIMIT = 30
   *
   * 1-30  -> authentication ทำงาน -> 401
   * 31-35 -> rate limit -> 429
   */

  const expectedStatus =
    attempt <= 30
      ? 401
      : 429;


  console.log(
    `Request ${attempt}` +
    ` | status=${response.status}` +
    ` | expected=${expectedStatus}`
  );


  check(
    response,
    {
      [`request ${attempt} => ${expectedStatus}`]:
        (res) =>
          res.status === expectedStatus,
    }
  );
}