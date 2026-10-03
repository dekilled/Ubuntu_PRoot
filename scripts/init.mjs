#!/usr/bin/env node
// Transforma o template num app novo: define id, nome e porta e atualiza os arquivos que os repetem.
//   npm run init -- --id com.suaempresa.meuapp --name "Meu App" [--port 8123]
// Depois de rodar isto você normalmente nunca mais precisa mexer em pacote Kotlin/Java: o
// applicationId e o nome do app são lidos do capacitor.config.json pelo Gradle.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const args = Object.fromEntries(
  process.argv.slice(2).flatMap((a, i, all) => (a.startsWith("--") ? [[a.slice(2), all[i + 1]]] : [])),
);
const fail = (msg) => {
  console.error(`✖ ${msg}\n\nUso: npm run init -- --id com.suaempresa.meuapp --name "Meu App" [--port 8123]`);
  process.exit(1);
};

const { id, name } = args;
const port = Number(args.port ?? 0) || undefined;
if (!id || !name) fail("Faltou --id e/ou --name.");
if (!/^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$/.test(id)) fail(`appId inválido: "${id}" (ex.: com.empresa.app; minúsculas, números e _ em cada parte).`);
if (port !== undefined && (port < 1024 || port > 65535)) fail("--port precisa estar entre 1024 e 65535.");

const read = (f) => JSON.parse(readFileSync(join(root, f), "utf8"));
const write = (f, data) => writeFileSync(join(root, f), JSON.stringify(data, null, 2) + "\n");

const cap = read("capacitor.config.json");
cap.appId = id;
cap.appName = name;
if (port) cap.plugins.ProotRuntime.port = port;
write("capacitor.config.json", cap);

const slug = name.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "app";
const pkg = read("package.json");
pkg.name = slug;
write("package.json", pkg);

const html = join(root, "frontend/index.html");
writeFileSync(html, readFileSync(html, "utf8").replace(/<title>.*<\/title>/, `<title>${name.replace(/[<&]/g, "")}</title>`));

const finalPort = cap.plugins.ProotRuntime.port;
writeFileSync(join(root, "frontend/.env"), `# Gerado por npm run init: onde o front (no navegador) encontra o servidor de desenvolvimento.\nVITE_DEV_BACKEND_URL=http://127.0.0.1:${finalPort}\n`);

console.log(`✔ ${name} (${id}) na porta ${finalPort}

Próximos passos:
  npm install
  npm run dev:backend   # servidor Python no PC       (terminal 1)
  npm run dev:web       # front no navegador          (terminal 2)
  npm run android:proot && npm run android:rootfs && npm run android:debug   # APK
`);
