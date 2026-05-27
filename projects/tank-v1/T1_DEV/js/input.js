const Input = {
  _pressed: new Set(),
  _justPressed: new Set(),

  init() {
    window.addEventListener('keydown', (e) => {
      if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' '].includes(e.key)) {
        e.preventDefault();
      }
      if (!this._pressed.has(e.key)) {
        this._justPressed.add(e.key);
      }
      this._pressed.add(e.key);
    });
    window.addEventListener('keyup', (e) => {
      this._pressed.delete(e.key);
    });
  },

  isDown(key) {
    return this._pressed.has(key);
  },

  isJustPressed(key) {
    return this._justPressed.has(key);
  },

  clearFrame() {
    this._justPressed.clear();
  },
};
