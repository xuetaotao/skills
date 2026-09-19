var auditPage = pages().find(function (candidate) { return !candidate.isClosed(); });
await auditPage.setViewportSize({ width: 760, height: 900 });
await auditPage.goto('file:///D:/Study/Demo/skills/stock/financial_report/output/bank-2026h1-comparison.html', { waitUntil: 'domcontentloaded' });
await expect.poll(async function () {
	return await auditPage.evaluate(function () { return typeof window.echarts; });
}, { timeout: 20000 }).toBe('object');
var chart = auditPage.locator('#chart5');
await chart.scrollIntoViewIfNeeded();
await expect(chart.locator('canvas')).toBeVisible();
await auditPage.waitForTimeout(1200);
var option = await chart.evaluate(function (element) {
	var instance = window.echarts.getInstanceByDom(element);
	return instance.getOption();
});
assert.equal(option.xAxis[0].data.length, 16);
assert(option.xAxis[0].data.indexOf('中国') >= 0);
assert.equal(option.series[1].data.length, 16);
var output = artifactPath('chart5-corrected.png');
await chart.screenshot({ path: output });
return { artifact: output, banks: option.xAxis[0].data, coverage: option.series[1].data };