export function indexGuide(data) {
  if (data.schema_version !== 1 || data.units !== 'mm' || data.sliced !== false
      || data.physical_fit_tested !== false || data.slot_numbers_are_physical_markings !== false) {
    throw new Error('未対応のデータ形式・検証状態です。正しいガイド一式を使ってください。');
  }
  const placements = new Map(data.placements.map((p) => [p.id, p]));
  const plates = new Map(data.plates.map((p) => [p.file, p]));
  const slots = new Map(data.plates.flatMap((p) => p.slots.map((s) => [s.id, { ...s, plate: p.file, color: p.color }])));
  if (placements.size !== data.part_count || slots.size !== data.part_count) {
    throw new Error('印刷個数と組立個数が一致しません。');
  }
  for (const slot of slots.values()) {
    const group = data.groups[slot.group];
    if (!group || !group.placements.includes(slot.suggested_placement)
        || JSON.stringify(group.placements) !== JSON.stringify(slot.candidate_placements)) {
      throw new Error('部品の対応表が不整合です。');
    }
  }
  return { placements, plates, slots };
}

const mix = (a, b, t) => a.map((n, i) => n + (b[i] - n) * t);
const smooth = (t) => t * t * (3 - 2 * t);

export function insertionPose(placement, progress, motion) {
  if (!Number.isFinite(progress) || progress < 0 || progress > 1) throw new RangeError('Invalid insertion progress');
  const final = { position: [...placement.position], rotation: [...placement.rotation] };
  if (progress === 1) return final;
  if (placement.role === 'front_module') {
    const front = motion.module_front_mm;
    const high = motion.module_lift_mm + 24;
    const waypoints = [
      { t: 0, offset: [0, -front, high], rotation: [0, 0, 0] },
      { t: .28, offset: [0, -front, high], rotation: placement.rotation },
      { t: .55, offset: [0, 0, motion.module_lift_mm], rotation: placement.rotation },
      { t: 1, offset: [0, 0, 0], rotation: placement.rotation },
    ];
    const end = waypoints.findIndex((w, i) => i > 0 && progress <= w.t);
    const from = waypoints[end - 1], to = waypoints[end];
    const t = smooth((progress - from.t) / (to.t - from.t));
    const offset = mix(from.offset, to.offset, t);
    return { position: placement.position.map((n, i) => n + offset[i]),
      rotation: mix(from.rotation, to.rotation, t) };
  }
  const lift = placement.role === 'keeper' ? motion.keeper_lift_mm : 26;
  return { position: placement.position.map((n, i) => n + (i === 2 ? lift * (1 - smooth(progress)) : 0)),
    rotation: [...placement.rotation] };
}

export function stepRange(data, number) {
  if (!Number.isInteger(number) || number < 0 || number > data.steps.length) throw new RangeError('Invalid step');
  if (number === 0) return [0, 0];
  const step = data.steps[number - 1];
  return [step.first_index, step.end_index];
}
