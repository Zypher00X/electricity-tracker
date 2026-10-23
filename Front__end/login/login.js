console.log("✅ login.js new version loaded");

document.addEventListener(
  "DOMContentLoaded",
  () => {

    const loginForm =
      document.getElementById("loginForm");

    const usernameInput =
      document.getElementById("username");

    const passwordInput =
      document.getElementById("password");

    const passwordToggle =
      document.getElementById("passwordToggle");

    const loginButton =
      document.getElementById("loginButton");

    const formMessage =
      document.getElementById("formMessage");


    console.log("loginForm:", loginForm);
    console.log("loginButton:", loginButton);


    if (!loginForm) {
      console.error("❌ loginForm not found");
      return;
    }


    // ==============================
    // SHOW / HIDE PASSWORD
    // ==============================

    if (passwordToggle && passwordInput) {

      passwordToggle.addEventListener(
        "click",
        () => {

          passwordInput.type =
            passwordInput.type === "password"
              ? "text"
              : "password";

        }
      );

    }


    // ==============================
    // MESSAGE
    // ==============================

    function showMessage(message, type) {

      if (!formMessage) {
        return;
      }

      formMessage.textContent = message;

      formMessage.className =
        `form-message ${type}`;
    }


    function clearMessage() {

      if (!formMessage) {
        return;
      }

      formMessage.textContent = "";

      formMessage.className =
        "form-message";
    }


    // ==============================
    // LOGIN
    // ==============================

    loginForm.addEventListener(
      "submit",
      async (event) => {

        event.preventDefault();

        console.log("🚀 Login form submitted");

        clearMessage();


        const identifier =
          usernameInput.value.trim();

        const password =
          passwordInput.value;


        if (!identifier) {

          showMessage(
            "กรุณากรอกอีเมลหรือเบอร์โทรศัพท์",
            "error"
          );

          return;
        }


        if (!password) {

          showMessage(
            "กรุณากรอกรหัสผ่าน",
            "error"
          );

          return;
        }


        try {

          loginButton.disabled = true;

          loginButton.textContent =
            "กำลังเข้าสู่ระบบ...";


          console.log(
            "🌐 Sending POST /api/auth/login"
          );


          const response =
            await fetch(
              "/api/auth/login",
              {
                method: "POST",

                headers: {
                  "Content-Type":
                    "application/json"
                },

                body: JSON.stringify({
                  identifier: identifier,
                  password: password
                })
              }
            );


          console.log(
            "📡 Login response status:",
            response.status
          );


          const result =
            await response.json();


          console.log(
            "📥 Login response:",
            result
          );


          // ==========================
          // LOGIN SUCCESS
          // ==========================

          if (response.ok) {

            console.log(
              "✅ Login successful:",
              result.user
            );


            showMessage(
              result.message ||
              "เข้าสู่ระบบสำเร็จ",
              "success"
            );


            setTimeout(
              () => {

                if (result.user.role === "admin") {

                  window.location.replace(
                    "/admin/dashboard"
                  );

                } else {

                  window.location.replace(
                    "/dashboard"
                  );
                }

              },
              600
            );


            return;
          }

          // ==========================
          // INVALID LOGIN
          // ==========================

          if (
            response.status === 401 ||
            response.status === 403
          ) {

            showMessage(
              result.detail ||
              "อีเมล/เบอร์โทรศัพท์หรือรหัสผ่านไม่ถูกต้อง",
              "error"
            );

            return;
          }


          // ==========================
          // OTHER ERROR
          // ==========================

          showMessage(
            result.detail ||
            "ไม่สามารถเข้าสู่ระบบได้",
            "error"
          );


        } catch (error) {

          console.error(
            "❌ Login error:",
            error
          );


          showMessage(
            "ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์ได้",
            "error"
          );


        } finally {

          loginButton.disabled =
            false;

          loginButton.textContent =
            "เข้าสู่ระบบ";

        }

      }
    );


    console.log(
      "✅ Login event listener ready"
    );

    // =====================================
    // GOOGLE LOGIN
    // =====================================

    const googleLoginButton =
      document.getElementById(
        "googleLoginButton"
      );


    if (googleLoginButton) {

      googleLoginButton.addEventListener(
        "click",
        () => {

          window.location.href =
            "/api/auth/google/start?mode=login";

        }
      );

    }

    // =====================================
    // GOOGLE OAUTH ERROR
    // =====================================

    const params =
      new URLSearchParams(
        window.location.search
      );


    const oauthError =
      params.get(
        "error"
      );


    if (oauthError) {

      const oauthErrorMessages = {

        google_account_not_found:
          "ยังไม่มีบัญชี PowerTrack สำหรับ Google Account นี้ กรุณาสมัครสมาชิกก่อน",

        account_inactive:
          "บัญชีผู้ใช้นี้ไม่สามารถใช้งานได้",

        google_state:
          "การยืนยันตัวตนหมดอายุ กรุณาลองเข้าสู่ระบบใหม่",

        google_oauth:
          "ไม่สามารถเข้าสู่ระบบด้วย Google ได้ กรุณาลองใหม่",

        google_account_exists:
          "บัญชี Google นี้สมัครสมาชิกแล้ว กรุณาเข้าสู่ระบบ",
      };


      const message =
        oauthErrorMessages[
          oauthError
        ];


      if (message) {

        showMessage(
          message,
          "error"
        );

      }

    }

  }
);

// =====================================
// AUTHENTICATED USER SHOULD NOT
// STAY ON LOGIN PAGE
// =====================================

window.addEventListener(
  "pageshow",
  async () => {

    try {

      const response =
        await fetch(
          "/api/auth/me",
          {
            method: "GET",

            credentials:
              "same-origin",

            cache:
              "no-store",

            headers: {
              "Accept":
                "application/json"
            }
          }
        );


      // ยังไม่ได้ Login
      if (!response.ok) {
        return;
      }


      const result =
        await response.json();


      const role =
        result.user.role;


      // User
      if (role === "user") {

        window.location.replace(
          "/dashboard"
        );

        return;
      }


      // Admin
      if (role === "admin") {

        window.location.replace(
          "/admin/dashboard"
        );

      }


    } catch (error) {

      console.error(
        "Auth state check failed:",
        error
      );

    }

  }
);