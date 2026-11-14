// mechanics.js — behavior registry. The ONLY file the model is allowed to write.
//
// Each behavior is a function (entity, scene, dt) called every frame for entities
// whose JSON lists it in "behaviors".
//   entity       Phaser sprite with arcade body (entity.body)
//   entity.def   the entity's level JSON
//   entity.props shortcut to entity.def.props (numbers/strings/bools)
//   entity.state per-entity scratch object (persists across frames, reset on restart)
//   scene        the GameScene: scene.player, scene.level, scene.TILE
//   dt           seconds since last frame
window.MECHANICS = window.MECHANICS || {};

// Walk back and forth around the spawn point; turn at walls or range edges.
MECHANICS.patrol = function (entity, scene, dt) {
  const s = entity.state;
  if (s.originX === undefined) { s.originX = entity.x; s.dir = -1; }
  const speed = entity.props.speed ?? 60;
  const range = (entity.props.range ?? 3) * scene.TILE;
  if (entity.body.blocked.left || entity.x < s.originX - range) s.dir = 1;
  else if (entity.body.blocked.right || entity.x > s.originX + range) s.dir = -1;
  entity.body.setVelocityX(speed * s.dir);
  entity.setFlipX(s.dir > 0);
};
