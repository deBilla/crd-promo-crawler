import express from "express";
import puppeteer from "puppeteer";

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());

let browser = null;

async function initBrowser() {
  if (!browser) {
    browser = await puppeteer.launch({
      headless: true,
      args: [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--single-process",
      ],
    });
  }
  return browser;
}

app.post("/render", async (req, res) => {
  const { url, wait_for, timeout } = req.body;

  if (!url) {
    return res.status(400).json({ error: "URL is required" });
  }

  let page = null;
  try {
    const browser = await initBrowser();
    page = await browser.newPage();

    const navigationTimeout = timeout || 30000;
    await page.setDefaultNavigationTimeout(navigationTimeout);
    await page.setDefaultTimeout(navigationTimeout);

    await page.setViewport({ width: 1920, height: 1080 });

    await page.goto(url, { waitUntil: "networkidle2" });

    if (wait_for) {
      try {
        await page.waitForSelector(wait_for, { timeout: 5000 });
      } catch (err) {
        console.warn(
          `Selector "${wait_for}" not found, continuing anyway`
        );
      }
    }

    const html = await page.content();
    const title = await page.title();
    const finalUrl = page.url();

    return res.json({
      html,
      title,
      final_url: finalUrl,
    });
  } catch (error) {
    console.error("Render error:", error);
    return res.status(500).json({
      error: error.message || "Failed to render page",
    });
  } finally {
    if (page) {
      try {
        await page.close();
      } catch (err) {
        console.error("Error closing page:", err);
      }
    }
  }
});

app.get("/health", (req, res) => {
  res.json({ status: "ok" });
});

app.listen(PORT, () => {
  console.log(`Puppeteer sidecar running on port ${PORT}`);
});

process.on("SIGTERM", async () => {
  console.log("SIGTERM received, closing browser...");
  if (browser) {
    await browser.close();
  }
  process.exit(0);
});
