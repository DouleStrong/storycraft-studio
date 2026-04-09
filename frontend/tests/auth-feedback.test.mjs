import test from "node:test";
import assert from "node:assert/strict";

import { getAuthErrorFeedback, getAuthValidationMessage, validateAuthFields } from "../auth-feedback.mjs";

test("getAuthValidationMessage explains that register mode still needs a pen name", () => {
  const message = getAuthValidationMessage("register", {
    name: "penName",
    validity: { valueMissing: true },
  });

  assert.equal(message, "请先填写笔名，再创建账号。");
});

test("getAuthValidationMessage explains invalid email input", () => {
  const message = getAuthValidationMessage("login", {
    name: "email",
    validity: { typeMismatch: true },
  });

  assert.equal(message, "请输入有效的邮箱地址。");
});

test("getAuthErrorFeedback guides the user to login when email already exists", () => {
  const feedback = getAuthErrorFeedback("register", "Email already registered");

  assert.deepEqual(feedback, {
    message: "该邮箱已经注册过了，已为你切换到登录模式。",
    tone: "warn",
    switchMode: "login",
  });
});

test("getAuthErrorFeedback returns a clear login failure message", () => {
  const feedback = getAuthErrorFeedback("login", "Invalid credentials");

  assert.deepEqual(feedback, {
    message: "邮箱或密码不正确，请再试一次。",
    tone: "error",
    switchMode: null,
  });
});

test("validateAuthFields requires a pen name in register mode", () => {
  const feedback = validateAuthFields("register", {
    email: "writer@example.com",
    password: "supersecret",
    penName: "",
  });

  assert.deepEqual(feedback, {
    field: "penName",
    message: "请先填写笔名，再创建账号。",
  });
});

test("validateAuthFields requires a valid email and password in login mode", () => {
  assert.deepEqual(
    validateAuthFields("login", {
      email: "broken-email",
      password: "supersecret",
      penName: "",
    }),
    {
      field: "email",
      message: "请输入有效的邮箱地址。",
    },
  );

  assert.deepEqual(
    validateAuthFields("login", {
      email: "writer@example.com",
      password: "123",
      penName: "",
    }),
    {
      field: "password",
      message: "密码至少需要 8 位。",
    },
  );
});

test("validateAuthFields returns null for valid login data", () => {
  assert.equal(
    validateAuthFields("login", {
      email: "writer@example.com",
      password: "supersecret",
      penName: "",
    }),
    null,
  );
});
