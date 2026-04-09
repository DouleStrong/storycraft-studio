export async function withSubmitForm(event, handler) {
  const form = event?.currentTarget;
  if (!form) {
    throw new Error("Form submission target is unavailable.");
  }
  return handler(form);
}
