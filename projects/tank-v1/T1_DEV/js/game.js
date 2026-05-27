const STATE_MENU = 'menu';
const STATE_PLAYING = 'playing';
const STATE_PAUSED = 'paused';
const STATE_VICTORY = 'victory';
const STATE_GAMEOVER = 'gameover';

class Game {
  constructor(canvas, hudEl, overlayEl) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.hudEl = hudEl;
    this.overlayEl = overlayEl;
    this.state = STATE_MENU;
    this.player = null;
    this.enemies = new EnemyController();
    this.bullets = [];
    this.walls = getWallRects();
  }

  start() {
    this.walls = getWallRects();
    this.player = new Tank(5 * CELL, 13 * CELL, DIR_UP, true, '#4a4', '#292');
    this.enemies = new EnemyController();
    this.enemies.spawnEnemies();
    this.bullets = [];
    this.state = STATE_PLAYING;
    this.overlayEl.style.display = 'none';
  }

  update() {
    if (this.state !== STATE_PLAYING) return;

    // Player input
    let moved = false;
    if (Input.isDown('ArrowUp')) {
      this.player.move(DIR_UP);
      moved = true;
    } else if (Input.isDown('ArrowDown')) {
      this.player.move(DIR_DOWN);
      moved = true;
    } else if (Input.isDown('ArrowLeft')) {
      this.player.move(DIR_LEFT);
      moved = true;
    } else if (Input.isDown('ArrowRight')) {
      this.player.move(DIR_RIGHT);
      moved = true;
    }

    // Player-wall collision
    if (moved && resolveTankWallCollision(this.player, this.walls)) {
      this.player.undoMove(this.player.direction);
    }

    // Player-enemy collision
    for (const enemy of this.enemies.getAliveTanks()) {
      if (resolveTankCollision(this.player, enemy)) {
        this.player.undoMove(this.player.direction);
        break;
      }
    }

    // Player shoot
    if (Input.isJustPressed(' ')) {
      const bullet = this.player.shoot();
      if (bullet) this.bullets.push(bullet);
    }

    this.player.update();

    // Enemies
    const enemyBullet = this.enemies.update(this.walls, this.player);
    if (enemyBullet) this.bullets.push(enemyBullet);

    // Bullets
    for (const bullet of this.bullets) {
      bullet.update(this.walls);
    }

    // Bullet-tank collisions
    for (const bullet of this.bullets) {
      if (!bullet.alive) continue;
      if (bullet.isFriendly) {
        for (const enemy of this.enemies.tanks) {
          if (bulletHitsTank(bullet, enemy)) {
            enemy.takeDamage();
            bullet.alive = false;
            break;
          }
        }
      } else {
        if (bulletHitsTank(bullet, this.player)) {
          this.player.takeDamage();
          bullet.alive = false;
        }
      }
    }

    // Clean dead bullets
    this.bullets = this.bullets.filter(b => b.alive);

    // Win/lose
    if (!this.player.alive) {
      this.state = STATE_GAMEOVER;
      this.overlayEl.style.display = 'flex';
      this.overlayEl.innerHTML = '<h1>GAME OVER</h1><p>按 Enter 返回菜单</p>';
    } else if (this.enemies.getAliveTanks().length === 0) {
      this.state = STATE_VICTORY;
      this.overlayEl.style.display = 'flex';
      this.overlayEl.innerHTML = '<h1>YOU WIN!</h1><p>按 Enter 返回菜单</p>';
    }

    // HUD
    this.hudEl.innerHTML =
      `HP: ${this.player.hp} | 剩余敌人: ${this.enemies.getAliveTanks().length}`;
  }

  draw() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.fillStyle = '#0a0a0a';
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    drawMap(ctx);
    this.player.draw(ctx);
    this.enemies.draw(ctx);
    for (const bullet of this.bullets) {
      bullet.draw(ctx);
    }
  }

  handleMenuInput() {
    if (Input.isJustPressed('Enter')) {
      if (this.state === STATE_MENU || this.state === STATE_VICTORY || this.state === STATE_GAMEOVER) {
        this.start();
      }
    }
    if (Input.isJustPressed('Escape') || Input.isJustPressed('p')) {
      if (this.state === STATE_PLAYING) {
        this.state = STATE_PAUSED;
        this.overlayEl.style.display = 'flex';
        this.overlayEl.innerHTML = '<h1>PAUSED</h1><p>按 Escape 继续</p>';
      } else if (this.state === STATE_PAUSED) {
        this.state = STATE_PLAYING;
        this.overlayEl.style.display = 'none';
      }
    }
  }
}
