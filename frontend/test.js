import puppeteer from 'puppeteer';

(async () => {
  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();
  
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', err => errors.push('PAGE_ERROR: ' + err.toString()));

  await page.goto('http://localhost:5173', { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 2000));
  
  // Check DOM rendered
  const hasRoot = await page.evaluate(() => {
    const root = document.getElementById('root');
    return root && root.children.length > 0;
  });
  
  // Check sidebar rendered
  const hasSidebar = await page.evaluate(() => {
    return document.querySelector('.sidebar') !== null;
  });

  console.log('=== RUNTIME CHECK ===');
  console.log('Root rendered:', hasRoot);
  console.log('Sidebar rendered:', hasSidebar);
  console.log('Page errors:', errors.filter(e => e.includes('PAGE_ERROR')).length);
  
  // Filter out expected network errors (backend may not be running)
  const realErrors = errors.filter(e => 
    e.includes('PAGE_ERROR') || 
    (e.includes('is not defined') || e.includes('Cannot read') || e.includes('Unexpected token'))
  );
  if (realErrors.length > 0) {
    console.log('CRITICAL ERRORS:');
    realErrors.forEach(e => console.log('  -', e));
  } else {
    console.log('No critical runtime errors!');
  }

  await browser.close();
})();
