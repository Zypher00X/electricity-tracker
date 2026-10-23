console.log("✅ register.js loaded");


document.addEventListener(
  "DOMContentLoaded",
  () => {

    console.log("✅ DOM loaded");


    // ======================================
    // ELEMENTS
    // ======================================

    const registerForm =
      document.getElementById("registerForm");

    const fullNameInput =
      document.getElementById("fullname");

    const emailInput =
      document.getElementById("email");

    const phoneInput =
      document.getElementById("phone");

    const passwordInput =
      document.getElementById("password");

    const passwordToggle =
      document.getElementById("passwordToggle");

    const registerButton =
      document.getElementById("registerButton");

    const formMessage =
      document.getElementById("formMessage");


    // ======================================
    // DEBUG ELEMENTS
    // ======================================

    console.log("registerForm:", registerForm);
    console.log("registerButton:", registerButton);


    // ถ้าหา Form ไม่เจอ
    if (!registerForm) {

      console.error(
        "❌ ไม่พบ element #registerForm"
      );

      return;
    }


    // ======================================
    // SHOW / HIDE PASSWORD
    // ======================================

    if (passwordToggle && passwordInput) {

      passwordToggle.addEventListener(
        "click",
        () => {

          const isHidden =
            passwordInput.type === "password";

          passwordInput.type =
            isHidden
              ? "text"
              : "password";

        }
      );

    }


    // ======================================
    // MESSAGE
    // ======================================

    function showMessage(
      message,
      type
    ) {

      if (!formMessage) {
        return;
      }

      formMessage.textContent =
        message;

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


    // ======================================
    // FORMAT VALIDATION ERROR
    // ======================================

    function getValidationMessage(
      detail
    ) {

      if (!Array.isArray(detail)) {

        return "ข้อมูลที่กรอกไม่ถูกต้อง";

      }

      return detail
        .map(
          (error) => error.msg
        )
        .join(", ");

    }


    // ======================================
    // REGISTER SUBMIT
    // ======================================

    registerForm.addEventListener(
      "submit",
      async (event) => {

        event.preventDefault();

        console.log(
          "🚀 Register form submitted"
        );


        clearMessage();


        // ==================================
        // FORM DATA
        // ==================================

        const fullName =
          fullNameInput.value.trim();

        const email =
          emailInput.value.trim();

        const phone =
          phoneInput.value.trim();

        const password =
          passwordInput.value;


        const registerData = {

          full_name: fullName,

          email: email,

          phone: phone,

          password: password

        };


        console.log(
          "📦 Register data:",
          {
            full_name: fullName,
            email: email,
            phone: phone,

            // ไม่ log password จริง
            password_length:
              password.length
          }
        );


        // ==================================
        // FRONTEND VALIDATION
        // ==================================

        if (!fullName) {

          showMessage(
            "กรุณากรอกชื่อ - นามสกุล",
            "error"
          );

          return;
        }


        if (!email) {

          showMessage(
            "กรุณากรอกอีเมล",
            "error"
          );

          return;
        }


        if (!phone) {

          showMessage(
            "กรุณากรอกเบอร์โทรศัพท์",
            "error"
          );

          return;
        }


        if (password.length < 8) {

          showMessage(
            "รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร",
            "error"
          );

          return;
        }


        try {

          // ==================================
          // LOADING
          // ==================================

          registerButton.disabled = true;

          registerButton.textContent =
            "กำลังสมัครสมาชิก...";


          console.log(
            "🌐 Sending POST /api/auth/register"
          );


          // ==================================
          // API REQUEST
          // ==================================

          const response =
            await fetch(
              "/api/auth/register",
              {

                method: "POST",

                headers: {
                  "Content-Type":
                    "application/json"
                },

                body:
                  JSON.stringify(
                    registerData
                  )

              }
            );


          console.log(
            "📡 Response status:",
            response.status
          );


          const result =
            await response.json();


          console.log(
            "📥 Response:",
            result
          );


          // ==================================
          // SUCCESS
          // ==================================

          if (response.ok) {

            showMessage(
              result.message ||
              "สมัครสมาชิกสำเร็จ",
              "success"
            );


            registerForm.reset();


            setTimeout(
              () => {

                window.location.href =
                  "/login";

              },
              1500
            );


            return;
          }


          // ==================================
          // DUPLICATE
          // ==================================

          if (
            response.status === 409
          ) {

            showMessage(
              result.detail ||
              "ข้อมูลนี้ถูกใช้งานแล้ว",
              "error"
            );

            return;
          }


          // ==================================
          // VALIDATION
          // ==================================

          if (
            response.status === 422
          ) {

            showMessage(
              getValidationMessage(
                result.detail
              ),
              "error"
            );

            return;
          }


          // ==================================
          // OTHER ERROR
          // ==================================

          showMessage(
            result.detail ||
            "ไม่สามารถสมัครสมาชิกได้",
            "error"
          );


        } catch (error) {

          console.error(
            "❌ Register error:",
            error
          );


          showMessage(
            "ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์ได้",
            "error"
          );


        } finally {

          registerButton.disabled =
            false;

          registerButton.textContent =
            "สมัครสมาชิก";

        }

      }
    );


    console.log(
      "✅ Register event listener ready"
    );

  }
);

const googleRegisterButton =
  document.getElementById(
    "googleRegisterButton"
  );


if (googleRegisterButton) {

  googleRegisterButton.addEventListener(
    "click",
    () => {

      window.location.href =
        "/api/auth/google/start?mode=register";

    }
  );

}