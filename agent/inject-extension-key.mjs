import crypto from "node:crypto";
import fs from "node:fs";

const [, , manifestPath, publicKeyPath, extensionIdPath] = process.argv;
if (!manifestPath || !publicKeyPath || !extensionIdPath) {
  throw new Error("usage: inject-extension-key.mjs <manifest> <public-key-der> <extension-id>");
}

const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const publicKey = fs.readFileSync(publicKeyPath);
const digest = crypto.createHash("sha256").update(publicKey).digest();
const extensionId = [...digest.subarray(0, 16)]
  .map((byte) => String.fromCharCode(97 + (byte >> 4), 97 + (byte & 0x0f)))
  .join("");

manifest.key = publicKey.toString("base64");
fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
fs.writeFileSync(extensionIdPath, `${extensionId}\n`);
