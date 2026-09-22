import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { indexGuide, insertionPose, stepRange } from '../web/assembly-guide/model.js';

const data = JSON.parse(readFileSync(new URL('../guide/index.mapping.json', import.meta.url), 'utf8'));

test('all 150 printed occurrences have both directions and all interchangeable candidates', () => {
  const index = indexGuide(data);
  assert.equal(index.slots.size, 150);
  assert.equal(index.placements.size, 150);
  assert.equal(index.plates.size, 14);
  for (const slot of index.slots.values()) {
    assert.deepEqual(slot.candidate_placements, data.groups[slot.group].placements);
    assert.equal(index.placements.get(slot.suggested_placement).suggested_source.slot_id, slot.id);
  }
  for (const placement of index.placements.values()) {
    assert.equal(index.slots.get(placement.suggested_source.slot_id).suggested_placement, placement.id);
  }
});

test('all 28 step ranges preserve the previous prefix without duplication', () => {
  let cursor = 0;
  assert.deepEqual(stepRange(data, 0), [0, 0]);
  for (const step of data.steps) {
    const [start, end] = stepRange(data, step.number);
    assert.equal(start, cursor);
    assert.deepEqual(data.placements.slice(start, end).map((part) => part.id), step.instances);
    cursor = end;
  }
  assert.equal(cursor, 150);
  assert.deepEqual(stepRange(data, 28), [150, 150]);
  for (const invalid of [-1, 29, 1.5, NaN]) assert.throws(() => stepRange(data, invalid), RangeError);
});

test('every insertion ends at the exact source position and rotation', () => {
  for (const placement of data.placements) {
    assert.deepEqual(insertionPose(placement, 1, data.motion), {
      position: placement.position, rotation: placement.rotation,
    });
    for (const progress of [0, .14, .28, .55, .75, 1]) {
      const pose = insertionPose(placement, progress, data.motion);
      assert.ok([...pose.position, ...pose.rotation].every(Number.isFinite));
    }
  }
  for (const progress of [-.1, 1.1, NaN, Infinity]) {
    assert.throws(() => insertionPose(data.placements[0], progress, data.motion), RangeError);
  }
});

test('front modules rotate from print-flat to 90 degrees before descending', () => {
  for (const id of ['B-020', 'B-021']) {
    const placement = data.placements.find((part) => part.id === id);
    assert.deepEqual(insertionPose(placement, 0, data.motion).rotation, [0, 0, 0]);
    assert.deepEqual(insertionPose(placement, .28, data.motion).rotation, [90, 0, 0]);
    const above = insertionPose(placement, .55, data.motion);
    assert.equal(above.position[0], placement.position[0]);
    assert.equal(above.position[1], placement.position[1]);
    assert.ok(above.position[2] - placement.position[2] >= 45);
    assert.deepEqual(above.rotation, placement.rotation);
  }
});

test('the unique first base and the fifth-course sources are not print-order guesses', () => {
  const index = indexGuide(data);
  assert.equal(data.first_source.slot_id, 'B-black-02.3mf#3');
  assert.deepEqual(index.slots.get('B-black-02.3mf#3').candidate_placements, ['B-001']);
  assert.deepEqual(index.slots.get('B-black-01.3mf#1').candidate_placements, ['B-006', 'B-015']);
  assert.equal(index.placements.get('B-016').suggested_source.slot_id, 'B-black-04.3mf#1');
  assert.equal(index.placements.get('B-017').suggested_source.slot_id, 'B-black-04.3mf#2');
  assert.deepEqual(data.parts['NP3-TEXT-B'].dimensions, [142, 40, 3.6]);
});
