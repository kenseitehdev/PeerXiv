// Template.js

export function renderTemplate(template, data = {}) {
	// Replace {{ prop }} in HTML with matching values from `data`
	return template.replace(/{{\s*([\w.]+)\s*}}/g, (_, key) => {
		const value = key.split('.').reduce((obj, part) => obj?.[part], data);
		return value !== undefined ? value : '';
	});
}
