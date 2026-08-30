import { invoke } from "@tauri-apps/api/core";

export const PROTOCOL_VERSION = "1.0";

export async function invokePetrolab(command, payload) {
  const envelope = {
    protocol_version: PROTOCOL_VERSION,
    request_id: crypto.randomUUID(),
    command,
    payload,
  };
  return invoke("petrolab_command", { envelope });
}
