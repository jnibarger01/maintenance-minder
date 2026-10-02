"use strict";

const SUBCODES = {
  1: ["Tire rotation", "Move the tires to different positions to help them wear more evenly. The rotation pattern depends on tire type and drivetrain."],
  2: ["Air filters + drive belt inspection", "Replace the engine air cleaner and cabin dust-and-pollen filter, and inspect the drive belt. These help keep intake air and cabin air clean."],
  3: ["Transmission fluid", "Replace the transmission fluid specified for this Honda. The exact procedure and fluid depend on transmission and model."],
  4: ["Spark plugs and related checks", "Replace spark plugs; inspect valve clearance. Replace a timing belt and inspect the water pump when the vehicle is equipped with a timing belt and the schedule calls for it."],
  5: ["Engine coolant", "Replace engine coolant according to the vehicle's schedule and use the specified coolant."],
  6: ["Rear differential fluid", "Replace rear differential fluid on equipped models, such as certain AWD vehicles."],
  7: ["Brake fluid", "Replace brake fluid according to the vehicle's Maintenance Minder and owner's manual."]
};

const MAIN_CODES = {
  A: {
    title: "Oil service",
    items: [["A", "Replace engine oil", "Fresh oil helps lubricate and protect moving engine parts. The oil type and quantity depend on the vehicle."]]
  },
  B: {
    title: "Oil service + inspections",
    items: [["B", "Replace engine oil and oil filter", "The filter is replaced with the oil to help capture contaminants. Honda also calls for scheduled inspections; the exact checklist depends on the vehicle."]]
  }
};

const SILHOUETTES = {
  sedan: "M20 59l7-19q3-7 13-9l13-11h51l19 17 19 4 8 9v15h-9a12 12 0 0 0-24 0H55a12 12 0 0 0-24 0H20z",
  hatch: "M20 59l8-20q3-8 13-9l19-12h39l20 14 22 6 8 10v11h-9a12 12 0 0 0-24 0H55a12 12 0 0 0-24 0H20z",
  suv: "M18 58l7-22q3-8 13-8h14l13-13h43l18 14 18 5 8 12v14h-9a12 12 0 0 0-24 0H54a12 12 0 0 0-24 0H18z",
  truck: "M18 58V31h83l17 14h23l10 9v10h-9a12 12 0 0 0-24 0H56a12 12 0 0 0-24 0H18zm102-13v-9l-10-10v19z",
  van: "M18 58V29q0-7 8-7h72l23 16h19q8 0 8 8v12h-9a12 12 0 0 0-24 0H54a12 12 0 0 0-24 0H18z",
  coupe: "M20 59l8-19q3-8 13-9l26-12h34l19 16 22 5 8 11v9h-9a12 12 0 0 0-24 0H55a12 12 0 0 0-24 0H20z"
};

const $ = (id) => document.getElementById(id);

// True only once a vehicle has actually been chosen (via link or controls).
// Until then the card must not assert a year and model the customer never picked.
let vehicleChosen = false;

// Vehicle catalogue, shared with the manifest generator via data/models.json.
let models = [];
let latestYear = new Date().getFullYear() + 1;
let earliestYear = 2015;

// Photo manifest, prebuilt by scripts/build_manifest.py.
let images = {};
let imagesLoaded = false;
let imagesFailed = false;

const otherTrimValue = "__other";
const defaultTrimValue = "__default__";

// Resolves a photo from the static manifest. Never reaches the network for
// metadata, so the page works from cache and offline once loaded.
function lookupImage(year, model, trim) {
  if (!imagesLoaded) return { found: false, reason: "still loading" };
  const exact = images[`${year}|${model}|${trim}`];
  if (exact && exact.found) return exact;
  // Custom trim names fall back to the vehicle's generic photo.
  const generic = images[`${year}|${model}|${defaultTrimValue}`];
  if (generic && generic.found) {
    // The generic entry was resolved for whichever trim matched, so it cannot
    // be presented as this customer's trim.
    return { ...generic, trimMatch: false };
  }
  return { found: false, reason: "no photo published for this year and model" };
}

function currentTrim() {
  const value = $("trimSelect").value;
  return value === otherTrimValue ? $("customTrim").value.trim() : value;
}

function selectedModel() {
  return models.find((model) => model.name === $("modelSelect").value) || models[0];
}

function trimsFor(model, year) {
  if (model.name !== "Clarity") return model.trims;
  if (year === 2017) return ["Fuel Cell"];
  if (year >= 2018 && year <= 2021) return ["Plug-In Hybrid", "Fuel Cell"];
  return [];
}

function availableModels(year) {
  return models.filter(
    (model) => year >= model.years[0] && year <= model.years[1] && !(model.exclude || []).includes(year)
  );
}

function silhouette(type, label) {
  const body = SILHOUETTES[type] || SILHOUETTES.sedan;
  return (
    `<svg viewBox="0 0 180 82" role="img" aria-label="Illustrative ${label} vehicle">` +
    `<path d="${body}" fill="#dce5e8" stroke="#617681" stroke-width="2"/>` +
    `<path d="M61 32l10-10h29l15 10z" fill="#f8fbfc" stroke="#71848d" stroke-width="1.5"/>` +
    `<circle cx="43" cy="63" r="9" fill="#253944"/><circle cx="43" cy="63" r="4" fill="#e7edef"/>` +
    `<circle cx="133" cy="63" r="9" fill="#253944"/><circle cx="133" cy="63" r="4" fill="#e7edef"/>` +
    `<path d="M22 53h13m103-7h10" stroke="#c92535" stroke-width="3" stroke-linecap="round"/></svg>`
  );
}

let photoRequest = 0;

function updateModelOptions() {
  const year = Number($("yearSelect").value);
  const list = availableModels(year);
  const previous = $("modelSelect").value;
  $("modelSelect").innerHTML = list.map((model) => `<option>${model.name}</option>`).join("");
  if (list.some((model) => model.name === previous)) $("modelSelect").value = previous;
  updateTrimOptions();
}

function updateTrimOptions() {
  const model = selectedModel();
  const year = Number($("yearSelect").value);
  const trims = trimsFor(model, year);
  $("trimSelect").innerHTML =
    '<option value="">Select trim</option>' +
    trims.map((trim) => `<option>${trim}</option>`).join("") +
    `<option value="${otherTrimValue}">Other / enter trim</option>`;
  $("customTrim").value = "";
  $("customTrim").hidden = true;
  syncVehicle();
}

function handleTrimChange() {
  const isOther = $("trimSelect").value === otherTrimValue;
  $("customTrim").hidden = !isOther;
  syncVehicle();
  if (isOther) $("customTrim").focus();
}

// Official Info Center colour swatches are natively ~164px wide. Below this the
// photo reads as a blurry artefact, so we fall back to the built-in silhouette.
const MIN_LEGIBLE_WIDTH = 240;

function syncVehicle() {
  const model = selectedModel();
  const year = $("yearSelect").value;
  const trim = currentTrim();
  const title = `${year} Honda ${model.name}`;

  $("vehicleName").textContent = title;
  $("vehicleTrimLabel").textContent =
    trim || ($("trimSelect").value === otherTrimValue ? "Type the trim" : "Choose a trim to refine the vehicle");
  $("footerVehicle").textContent = vehicleChosen ? `${year} • ${model.name}` : "Maintenance Minder";

  if (vehicleChosen) {
    $("customerVehicle").textContent = title;
    $("customerTrim").textContent = trim || "Trim not selected";
    document.body.classList.add("has-vehicle");
  }

  const request = ++photoRequest;
  const hit = lookupImage(year, model.name, trim);
  const label = $("imageLabel");
  const note = $("imageUnavailable");
  const carImage = $("carImage");
  const carFallback = $("carFallback");
  const miniImage = $("miniImage");
  const miniFallback = $("miniFallback");
  const miniNote = $("miniUnavailable");

  const reset = () => {
    [carImage, miniImage, carFallback, miniFallback].forEach((node) => { node.hidden = true; });
    label.textContent = "Finding official Honda photo…";
    label.href = "https://www.hondainfocenter.com/";
    note.hidden = false;
    miniNote.hidden = false;
  };

  const showSilhouette = (message, credit) => {
    if (request !== photoRequest) return;
    carImage.hidden = true;
    miniImage.hidden = true;
    carFallback.innerHTML = silhouette(model.type, model.name);
    carFallback.hidden = false;
    miniFallback.innerHTML = silhouette(model.type, model.name);
    miniFallback.hidden = false;
    if (credit) {
      label.textContent = credit.credit;
      label.href = credit.source;
    } else {
      label.textContent = "No official photo for this year";
      label.href = "https://www.hondainfocenter.com/";
    }
    note.textContent = message;
    miniNote.hidden = true;
  };

  // Credits a photo that is the right year and model but not this exact trim.
  const trimLabel = hit.trimMatch === false
    ? `${hit.credit} · model shown, not your trim`
    : hit.credit;

  reset();

  if (!hit.found) {
    if (imagesFailed) {
      showSilhouette("The photo library could not be loaded.");
    } else if (imagesLoaded) {
      showSilhouette(hit.reason ? `${hit.reason}.` : "No matching official photo was found.");
    }
    return;
  }

  // The photo exists and is credited, but is too small to render cleanly.
  // Show the silhouette while keeping the link to the official image.
  if ((hit.width || 0) && hit.width < MIN_LEGIBLE_WIDTH) {
    showSilhouette(
      "Honda publishes this photo only as a small swatch, so an illustration is shown here. Follow the credit to view the official image.",
      { credit: trimLabel, source: hit.source }
    );
    return;
  }

  note.textContent =
    hit.trimMatch === false
      ? "This is your model year. Honda hasn't published a photo of this exact trim yet."
      : "Loading official Honda photo…";
  const onReady = () => {
    if (request !== photoRequest) return;
    carImage.hidden = false;
    miniImage.hidden = false;
    note.hidden = true;
    miniNote.hidden = true;
  };
  const onError = () => {
    if (request !== photoRequest) return;
    label.textContent = "Honda image could not load";
    note.textContent = "The official image was found but could not be loaded. Try re-selecting the vehicle.";
    miniNote.textContent = "Image unavailable";
  };
  carImage.onload = onReady;
  miniImage.onload = onReady;
  carImage.onerror = onError;
  miniImage.onerror = onError;
  carImage.alt = `${title}${trim ? " " + trim : ""} reference thumbnail`;
  miniImage.alt = carImage.alt;
  label.textContent = trimLabel;
  label.href = hit.source;
  carImage.src = hit.image;
  miniImage.src = hit.image;
}

function renderCode() {
  const raw = $("codeInput").value.toUpperCase().replace(/\s/g, "");
  $("codeInput").value = raw;
  const match = raw.match(/^([AB])([1-7]*)$/);
  const status = $("codeStatus");

  if (!match) {
    status.textContent = "!";
    status.classList.add("invalid");
    status.setAttribute("aria-label", "Enter A or B followed by optional subcodes 1 through 7");
    $("codeBadge").textContent = raw || "—";
    $("codeTitle").textContent = "Enter a valid reminder code";
    $("codeSubtext").textContent = "Use the letter and numbers shown on the dashboard, such as A1 or B12.";
    $("serviceList").innerHTML =
      '<div class="service-item"><span class="item-code">?</span><div><h4>Check the dashboard message</h4>' +
      "<p>Use A or B followed by any displayed subcodes 1–7. The code is a maintenance reminder, not a warning light diagnosis.</p></div></div>";
    return;
  }

  status.textContent = "✓";
  status.classList.remove("invalid");
  status.setAttribute("aria-label", "Valid code");

  const main = match[1];
  const digits = [...new Set(match[2].split(""))];
  let title = main === "A" ? "Oil service" : "Oil service + inspections";
  if (digits.length) {
    title += (main === "A" ? " + " : " + ") + digits.map((n) => SUBCODES[n][0]).join(" + ");
  }

  $("codeBadge").textContent = raw;
  $("codeTitle").textContent = title;
  $("codeSubtext").textContent = "Honda's Maintenance Minder groups the items due for this vehicle.";

  const items = MAIN_CODES[main].items.map((item) => ({ code: item[0], title: item[1], desc: item[2] }));
  digits.forEach((n) => items.push({ code: n, title: SUBCODES[n][0], desc: SUBCODES[n][1] }));

  $("serviceList").innerHTML = items
    .map(
      (item) =>
        '<article class="service-item"><span class="item-code"></span><div><h4></h4><p></p></div></article>'
    )
    .join("");
  // Populate via textContent so entered data is never interpreted as markup.
  $("serviceList")
    .querySelectorAll(".service-item")
    .forEach((node, index) => {
      node.querySelector(".item-code").textContent = items[index].code;
      node.querySelector("h4").textContent = items[index].title;
      node.querySelector("p").textContent = items[index].desc;
    });
}

function toggleVehiclePanel() {
  const panel = $("vehiclePanel");
  const open = panel.hidden;
  panel.hidden = !open;
  document.body.classList.toggle("vehicle-open", open);
  $("vehicleToggle").setAttribute("aria-expanded", String(open));
  $("vehicleToggle").firstChild.textContent = open ? "Hide vehicle " : "My vehicle ";
  if (open) {
    const params = new URLSearchParams(location.search);
    if (params.get("model")) {
      panel.hidden = false;
    } else {
      $("yearSelect").focus();
    }
  }
}

function readCodeFromQuery() {
  const code = new URLSearchParams(location.search).get("code");
  if (!code) return;
  const clean = code.toUpperCase().replace(/[^AB1-7]/g, "");
  if (clean) {
    $("codeInput").value = clean;
    renderCode();
  }
}

function markVehicleChosen() {
  vehicleChosen = true;
  syncVehicle();
}

function readVehicleFromQuery() {
  const params = new URLSearchParams(location.search);
  const year = params.get("year");
  const model = params.get("model");
  const trim = params.get("trim");
  if (year && models.some((m) => year >= m.years[0] && year <= m.years[1])) {
    $("yearSelect").value = year;
    updateModelOptions();
  }
  if (model && models.some((m) => m.name === model)) {
    $("modelSelect").value = model;
    updateTrimOptions();
    vehicleChosen = true;
  }
  if (trim) {
    const option = [...$("trimSelect").options].find((o) => o.value === trim);
    if (option && option.value !== otherTrimValue) $("trimSelect").value = trim;
    else {
      $("trimSelect").value = otherTrimValue;
      $("customTrim").hidden = false;
      $("customTrim").value = trim;
    }
    vehicleChosen = true;
    syncVehicle();
  }
}

function syncUrl() {
  const params = new URLSearchParams();
  params.set("year", $("yearSelect").value);
  params.set("model", $("modelSelect").value);
  const trim = currentTrim();
  if (trim) params.set("trim", trim);
  const code = $("codeInput").value.trim();
  if (code) params.set("code", code);
  history.replaceState(null, "", `?${params.toString()}`);
}

async function loadManifest() {
  try {
    const response = await fetch("images.json", { cache: "no-cache" });
    if (!response.ok) throw new Error(`status ${response.status}`);
    const payload = await response.json();
    images = payload.entries || {};
    imagesLoaded = true;
  } catch (error) {
    imagesFailed = true;
    imagesLoaded = true;
  }
  syncVehicle();
}

async function init() {
  try {
    const response = await fetch("data/models.json", { cache: "no-cache" });
    const spec = await response.json();
    models = spec.models;
    latestYear = spec.latestYear;
    earliestYear = spec.earliestYear;
  } catch (error) {
    $("vehicleName").textContent = "Vehicle data unavailable";
  }

  const years = Array.from({ length: latestYear - earliestYear + 1 }, (_, i) => latestYear - i);
  years.forEach((year) => $("yearSelect").add(new Option(year, year)));
  $("yearSelect").value = String(Math.min(latestYear, new Date().getFullYear()));
  updateModelOptions();

  $("modelSelect").addEventListener("change", () => { updateTrimOptions(); markVehicleChosen(); syncUrl(); });
  $("yearSelect").addEventListener("change", () => { updateModelOptions(); markVehicleChosen(); syncUrl(); });
  $("trimSelect").addEventListener("change", () => { handleTrimChange(); markVehicleChosen(); syncUrl(); });
  $("customTrim").addEventListener("input", () => { markVehicleChosen(); syncVehicle(); syncUrl(); });
  $("codeInput").addEventListener("input", () => { renderCode(); syncUrl(); });
  document.querySelectorAll("[data-code]").forEach((button) =>
    button.addEventListener("click", () => { $("codeInput").value = button.dataset.code; renderCode(); syncUrl(); })
  );
  $("printBtn").addEventListener("click", () => window.print());
  $("copyBtn").addEventListener("click", copySummary);
  $("vehicleToggle").addEventListener("click", toggleVehiclePanel);

  renderCode();
  readVehicleFromQuery();
  readCodeFromQuery();
  // A shared link that names a vehicle opens the panel so the photo is visible.
  if (new URLSearchParams(location.search).get("model")) {
    $("vehiclePanel").hidden = false;
    document.body.classList.add("vehicle-open");
    $("vehicleToggle").setAttribute("aria-expanded", "true");
    $("vehicleToggle").firstChild.textContent = "Hide vehicle ";
  }
  await loadManifest();
}

async function copySummary() {
  const lines = [
    $("codeBadge").textContent + " — " + $("codeTitle").textContent,
    $("customerVehicle").textContent + ($("customerTrim").textContent !== "Trim not selected" ? " " + $("customerTrim").textContent : ""),
    "",
    ...[...$("serviceList").querySelectorAll(".service-item")].map(
      (node) => `${node.querySelector(".item-code").textContent} · ${node.querySelector("h4").textContent}`
    )
  ];
  const button = $("copyBtn");
  try {
    await navigator.clipboard.writeText(lines.join("\n"));
    button.querySelector("span").textContent = "Copied";
    setTimeout(() => { button.querySelector("span").textContent = "Copy"; }, 1800);
  } catch (error) {
    button.querySelector("span").textContent = "Copy failed";
  }
}

init();