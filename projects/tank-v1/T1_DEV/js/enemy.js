const ENEMY_DIR_CHANGE_INTERVAL = 90; // frames between random direction changes
const ENEMY_SHOOT_INTERVAL = 100;       // frames between enemy shots

class EnemyController {
  constructor() {
    this.tanks = [];
    this.dirTimers = [];
    this.shootTimers = [];
  }

  spawnEnemies() {
    const spawns = [
      { x: 8 * CELL, y: 0 },
      { x: 15 * CELL, y: 0 },
      { x: 0, y: 8 * CELL },
      { x: 16 * CELL, y: 8 * CELL },
      { x: 8 * CELL, y: 12 * CELL },
    ];
    for (const s of spawns) {
      const tank = new Tank(s.x, s.y, DIR_DOWN, false, '#c44', '#a22');
      this.tanks.push(tank);
      this.dirTimers.push(Math.floor(Math.random() * ENEMY_DIR_CHANGE_INTERVAL));
      this.shootTimers.push(Math.floor(Math.random() * ENEMY_SHOOT_INTERVAL));
    }
  }

  getAliveTanks() {
    return this.tanks.filter(t => t.alive);
  }

  update(walls, playerTank) {
    const allTanks = [playerTank, ...this.tanks];

    for (let i = 0; i < this.tanks.length; i++) {
      const tank = this.tanks[i];
      if (!tank.alive) continue;

      tank.update();

      // Random direction change
      this.dirTimers[i] -= 1;
      if (this.dirTimers[i] <= 0) {
        this.dirTimers[i] = ENEMY_DIR_CHANGE_INTERVAL + Math.floor(Math.random() * 60);
        tank.direction = Math.floor(Math.random() * 4);
      }

      // Move
      tank.move(tank.direction);

      // Wall collision — undo and pick new direction
      if (resolveTankWallCollision(tank, walls)) {
        tank.undoMove(tank.direction);
        // Try the 4 directions in random order
        const dirs = [0, 1, 2, 3].sort(() => Math.random() - 0.5);
        let moved = false;
        for (const d of dirs) {
          tank.direction = d;
          tank.move(d);
          if (!resolveTankWallCollision(tank, walls)) {
            moved = true;
            break;
          }
          tank.undoMove(d);
        }
        if (!moved) {
          tank.undoMove(tank.direction);
        }
      }

      // Collision with other enemies — undo
      let blocked = false;
      for (const other of allTanks) {
        if (other === tank || !other.alive) continue;
        if (resolveTankCollision(tank, other)) {
          blocked = true;
          break;
        }
      }
      if (blocked) {
        tank.undoMove(tank.direction);
      }

      // Shooting
      this.shootTimers[i] -= 1;
      if (this.shootTimers[i] <= 0) {
        this.shootTimers[i] = ENEMY_SHOOT_INTERVAL + Math.floor(Math.random() * 80);
        return tank.shoot();
      }
    }
    return null;
  }

  draw(ctx) {
    for (const tank of this.tanks) {
      tank.draw(ctx);
    }
  }
}
