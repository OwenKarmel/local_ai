// mechanics.js — behavior registry. The ONLY file the model is allowed to write.
//
// Each behavior is a function (entity, scene, dt) called every frame for entities
// whose JSON lists it in "behaviors".
//   entity       Phaser sprite with arcade body (entity.body)
//   entity.def   the entity's level JSON
//   entity.props shortcut to entity.def.props (numbers/strings/bools)
//   entity.state per-entity scratch object (persists across frames, reset on restart)
//   scene        the GameScene: scene.player, scene.level, scene.TILE,
//                scene.isBig / scene.setPlayerBig(on) (taller player with a different look that survives one hit),
//                scene.hurt(reason) (shrinks a big player, otherwise kills),
//                scene.enemyHp(e) / scene.damageEnemy(e, n) / scene.defeatEnemy(e) (enemies take props.hp hits),
//                scene.spawnEnemyShot(x, y, vx, vy, {sprite, tint}) (projectile that hurts the player),
//                scene.solidAt(px, py) (is this world point inside a platform?),
//                scene.showToast(text), scene.ring(x, y, color, size), scene.cameras.main.shake(ms, amount)
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

// Two-phase boss. Walks its platform (turns at walls and ledges) and hops every props.jump_every seconds.
// Phase 2 starts once its hp left (scene.enemyHp) drops to props.phase2_at: it turns red, walks at
// props.phase2_speed and shoots at the player every props.shoot_every seconds. Every prop can change live.
MECHANICS.boss = function (entity, scene, dt) {
  const s = entity.state, p = entity.props, b = entity.body;
  if (s.dir === undefined) { s.dir = -1; s.hopT = 0; s.shotT = 0; s.phase = 1; }
  const phase = scene.enemyHp(entity) <= (p.phase2_at ?? 0) ? 2 : 1;
  if (phase !== s.phase) {
    s.phase = phase;
    if (phase === 2) {
      entity.setTint(0xff6a5a);
      scene.cameras.main.shake(350, 0.01);
      scene.ring(entity.x, entity.y, 0xff6a5a, 14);
      scene.showToast(`${entity.def.id}: phase 2!`);
      if (b.blocked.down) b.setVelocityY(-480); // angry leap
    } else {
      SPRITES.applyTint(entity, entity.look, entity.def.tint); // hp raised live: back to phase 1 colors
    }
  }

  const onGround = b.blocked.down;
  if (b.blocked.left) s.dir = 1;
  else if (b.blocked.right) s.dir = -1;
  else if (onGround && !scene.solidAt(s.dir > 0 ? b.right + 4 : b.left - 4, b.bottom + 4)) s.dir = -s.dir; // ledge ahead

  const every = p.jump_every ?? 0;
  s.hopT += dt;
  if (every > 0 && s.hopT >= every && onGround) { s.hopT = 0; b.setVelocityY(-420); }

  const shootEvery = p.shoot_every ?? 0;
  if (phase === 2 && shootEvery > 0) {
    s.shotT += dt;
    if (s.shotT >= shootEvery) {
      s.shotT = 0;
      const pl = scene.player, dx = pl.x - entity.x, dy = pl.y - entity.y, d = Math.hypot(dx, dy) || 1;
      const v = p.shot_speed ?? 260;
      scene.spawnEnemyShot(entity.x + Math.sign(dx || 1) * (b.width / 2 + 6), entity.y - 6, (dx / d) * v, (dy / d) * v);
    }
  }

  b.setVelocityX((phase === 2 ? p.phase2_speed ?? 140 : p.speed ?? 70) * s.dir);
  entity.setFlipX(s.dir > 0);
};
