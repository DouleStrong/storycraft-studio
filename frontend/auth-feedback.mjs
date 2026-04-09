export function getAuthValidationMessage(authMode, field) {
  const name = field?.name || "";
  const validity = field?.validity || {};

  if (validity.valueMissing) {
    if (name === "penName" && authMode === "register") {
      return "请先填写笔名，再创建账号。";
    }
    if (name === "email") {
      return "请先填写邮箱地址。";
    }
    if (name === "password") {
      return authMode === "login" ? "请先输入密码，再继续登录。" : "请先设置密码，再创建账号。";
    }
  }

  if (validity.typeMismatch && name === "email") {
    return "请输入有效的邮箱地址。";
  }

  if (validity.tooShort && name === "password") {
    return "密码至少需要 8 位。";
  }

  return authMode === "login" ? "请检查登录信息后再试一次。" : "请先补全注册信息。";
}

export function validateAuthFields(authMode, fields) {
  const email = String(fields?.email || "").trim();
  const password = String(fields?.password || "");
  const penName = String(fields?.penName || "").trim();

  if (!email) {
    return { field: "email", message: "请先填写邮箱地址。" };
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return { field: "email", message: "请输入有效的邮箱地址。" };
  }
  if (!password) {
    return {
      field: "password",
      message: authMode === "login" ? "请先输入密码，再继续登录。" : "请先设置密码，再创建账号。",
    };
  }
  if (password.length < 8) {
    return { field: "password", message: "密码至少需要 8 位。" };
  }
  if (authMode === "register" && !penName) {
    return { field: "penName", message: "请先填写笔名，再创建账号。" };
  }
  return null;
}

export function getAuthErrorFeedback(authMode, rawMessage) {
  const message = String(rawMessage || "");

  if (message.includes("Email already registered")) {
    return {
      message: "该邮箱已经注册过了，已为你切换到登录模式。",
      tone: "warn",
      switchMode: "login",
    };
  }

  if (message.includes("Invalid credentials")) {
    return {
      message: "邮箱或密码不正确，请再试一次。",
      tone: "error",
      switchMode: null,
    };
  }

  if (message.includes("Failed to fetch")) {
    return {
      message: "暂时连接不到后端服务，请确认 API 已启动。",
      tone: "error",
      switchMode: null,
    };
  }

  return {
    message: authMode === "login" ? "登录没有成功，请稍后再试。" : "注册没有成功，请稍后再试。",
    tone: "error",
    switchMode: null,
  };
}
