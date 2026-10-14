const express = require("express");
const path = require("path");
const XLSX = require("xlsx");

const app = express();
const PORT = 5000;

// Set EJS as the view engine
app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "views"));

// Serve static files (if any)
app.use(express.static(path.join(__dirname, "public")));

// Helper function to read Excel and extract relevant data
function getRestaurantDataOSM() {
  try {
    const workbook = XLSX.readFile(path.join(__dirname, "..", "tst.xlsx"));
    const sheetName = workbook.SheetNames[0]; // First sheet
    const sheet = workbook.Sheets[sheetName];
    const jsonData = XLSX.utils.sheet_to_json(sheet);

    // Ensure data has the required fields for mapping
    return jsonData.map((item) => {
      return {
        ...item,
        lat: item.lat || item.latitude || item.Latitude || item.LAT,
        lng: item.lng || item.longitude || item.Longitude || item.LNG,
        name: item.name || item.Name || item.NAME || "Unnamed Location",
        City: item.City || item.city || "Unknown",
        Category: item.Category || item.category || "Food and Beverages", // Default category
      };
    });
  } catch (error) {
    console.error("Error reading tst.xlsx:", error);
    return [];
  }
}
function getRestaurantDataGoogleMaps() {
  try {
    const workbook = XLSX.readFile(
      path.join(__dirname, "..", "Erbil_markets_multithread.xlsx")
    );
    const sheetName = workbook.SheetNames[0]; // First sheet (Google Maps data)
    const sheet = workbook.Sheets[sheetName];
    const jsonData = XLSX.utils.sheet_to_json(sheet);

    // Ensure data has the required fields for mapping
    return jsonData.map((item) => {
      return {
        ...item,
        lat: item.lat || item.latitude || item.Latitude || item.LAT,
        lng: item.lng || item.longitude || item.Longitude || item.LNG,
        name: item.name || item.Name || item.NAME || "Unnamed Location",
        City: item.City || item.city || "Unknown",
        Category: item.Category || item.category || "Food and Beverages", // Default category
      };
    });
  } catch (error) {
    console.error("Error reading Erbil_markets_multithread.xlsx:", error);
    return [];
  }
}
// Root route
app.get("/", (req, res) => {
  res.render("index");
});

// API endpoint for restaurant data
app.get("/api/restaurantsOSM", (req, res) => {
  const restaurantData = getRestaurantDataOSM();
  res.json(restaurantData);
});
app.get("/api/restaurantsGoogleMaps", (req, res) => {
  const restaurantData = getRestaurantDataGoogleMaps();
  res.json(restaurantData);
});

app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});
