// Run with: node --test tests/product.test.cjs
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');
const script = html.match(/<script type="module">([\s\S]*?)<\/script>/)[1];
const context = vm.createContext({
  document: {addEventListener() {}},
  window: {location: {protocol:'http:', pathname:'/app', origin:'http://127.0.0.1:8000'}},
  console: {info() {}, log() {}, assert(condition, message) {assert.ok(condition, message);}}, Intl, Date, URLSearchParams,
});
vm.runInContext(script + '\nglobalThis.api = {productRecommendation, renderMenu, renderHome};', context);
const result = (type='high_gas', status='ready') => ({
  profile: {home: {energy_label: null}, fuels: {gas_m3: {status}, electricity_kwh: {status}}},
  events: [{type, start:'2013-01-16T00:00:00', magnitude:10, confidence:0.8}],
  advice_context: {allow_heating_reduction:false},
});

test('gas recommendation uses real profile context and withholds heating reduction', () => {
  const advice = context.api.productRecommendation(result());
  assert.ok(advice);
  assert.equal(advice.tip.heating, false);
  assert.equal(advice.tip.conditions.event, 'high_gas');
  assert.equal(advice.tip.euroPerPersonPerYear, undefined);
});
test('electricity event selects an electricity tip', () => {
  const advice = context.api.productRecommendation(result('high_electricity'));
  assert.equal(advice.tip.conditions.event, 'high_electricity');
});
test('insufficient history or no event withholds event-based advice', () => {
  assert.equal(context.api.productRecommendation(result('high_gas', 'insufficient_history')), null);
  const empty = result(); empty.events = [];
  assert.equal(context.api.productRecommendation(empty), null);
});
test('switching household results cannot reuse a previous recommendation', () => {
  assert.ok(context.api.productRecommendation(result()));
  const next = result(); next.events = [];
  assert.equal(context.api.productRecommendation(next), null);
});
test('menu distinguishes research data from the simulated game', () => {
  const menu = context.api.renderMenu('en');
  assert.match(menu, /data-menu="product"/);
  assert.match(menu, /simulated data/);
});
