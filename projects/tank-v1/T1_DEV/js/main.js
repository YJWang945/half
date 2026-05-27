(function () {
  const canvas = document.getElementById('gameCanvas');
  const hudEl = document.getElementById('hud');
  const overlayEl = document.getElementById('overlay');
  const game = new Game(canvas, hudEl, overlayEl);

  Input.init();

  function loop() {
    game.handleMenuInput();
    game.update();
    game.draw();
    Input.clearFrame();
    requestAnimationFrame(loop);
  }

  overlayEl.innerHTML = '<h1>TANK BATTLE</h1><p>按 Enter 开始游戏</p><p>方向键移动 | 空格射击 | Esc 暂停</p>';
  loop();
})();
