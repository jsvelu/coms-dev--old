"use strict";
var webpack = require('webpack');
var WebpackDevServer = require('webpack-dev-server');
var config = require('./webpack.config.dev');

var devServerWebpackConfig = config({hotmod: true});
// TODO: Was this needed?
//var watcherWebpackConfig = config({hotmod: false});

new WebpackDevServer(webpack(devServerWebpackConfig), {
	publicPath: devServerWebpackConfig.output.publicPath,
	hot: true,
	inline: true,
	historyApiFallback: true
}).listen(3011, '0.0.0.0', function (err, result) {
	if (err) console.log(err);
	console.log('Listening at 0.0.0.0:3011');
});
