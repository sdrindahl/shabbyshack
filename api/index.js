const express = require('express');

const app = express();

app.get('/ping', (req, res) => {
  res.json({ message: 'pong' });
});

const PORT = process.env.PORT || 8080;
console.log('process.env.PORT:', process.env.PORT);
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
