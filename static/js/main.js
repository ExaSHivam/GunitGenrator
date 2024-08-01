console.log('main.js loaded');

// Selecting DOM elements
const gunitInput = document.getElementById('lob-input');
const output = document.getElementById('output');
const dropdownID = document.getElementById('lob_select');
const gunitForm = document.getElementById('gunit-input');
const baseMethodInput = document.getElementById('base_method_input');
const classNameInput = document.getElementById('class_name_input');
let uploadBtn;

let gunitInputDisplayed = false;
//  function initiateLoader(){
//        document.getElementById('loader').hidden = false;
//    }

function showGunitInput() {
    if (gunitInput && !gunitInputDisplayed) {
        gunitInput.style.display = 'block';
        if (output) {
            output.style.display = 'none';

        }
        gunitInputDisplayed = true;
    }
}

function showGunitInputAndForm() {
    if (gunitInput && gunitForm) {
        gunitInput.style.display = 'block';
        gunitForm.style.display = 'block';
        if (output) {
            output.style.display = 'none';
        }
        gunitInputDisplayed = true;
    }
}

// Add event listeners for radio buttons
document.getElementById('base_method').addEventListener('change', function() {
    baseMethodInput.style.display = 'block';
    classNameInput.style.display = 'none';
});

document.getElementById('class').addEventListener('change', function() {
    baseMethodInput.style.display = 'none';
    classNameInput.style.display = 'block';
});

function autoSize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = (Math.min(textarea.scrollHeight, 300)) + 'px';
}

// Add event listeners to dynamically resize textareas
function copyToClipboard(id) {
    var textarea = document.getElementById(id);
    textarea.select();
    textarea.setSelectionRange(0, 99999); // For mobile devices

    try {
        var successful = document.execCommand('copy');
        var msg = successful ? 'successful' : 'unsuccessful';
        console.log('Copying text command was ' + msg);
    } catch (err) {
        console.error('Oops, unable to copy', err);
    }
}

document.addEventListener("DOMContentLoaded", function() {
    document.querySelector('.menu a').addEventListener('click', (event) => {
        event.preventDefault();
        showGunitInput();
    });

    dropdownID.addEventListener('change', function(event) {
        const selectedLOB = event.target.value;
        console.log("Selected Line of Business:", selectedLOB);
        if (selectedLOB && selectedLOB !== "") {
            console.log("entered Line of Business:", selectedLOB);
            document.getElementById("selected_lob").value = selectedLOB;

            showGunitInputAndForm();
        } else {
            console.log("did not enter Line of Business:", selectedLOB);
            gunitInput.style.display = 'none';
            gunitForm.style.display = 'none';
            gunitInputDisplayed = false;
        }
    });

    document.querySelectorAll('input[name="gunit_type"]').forEach((radio) => {
        radio.addEventListener('change', function(event) {
            if (event.target.value === 'base_method') {
                baseMethodTextarea.style.display = 'block';
            } else {
                baseMethodTextarea.style.display = 'none';
            }
        });
    });

    uploadBtn = document.getElementById('upload-gunit');

    uploadBtn.addEventListener('click', (event) => {
        event.preventDefault();
        if (validateForm()) {
            document.querySelector('.upload-gunit').submit();
//            initiateLoader();

        }
    });
});

function validateForm() {
    let isValid = true;
    const lob = document.getElementById('lob');
    const builder = document.getElementById('builder');
    const features = document.querySelectorAll('input[name="features"]:checked');
    const gunitType = document.querySelectorAll('input[name="gunit_type"]:checked');
    const baseMethodTextarea = document.getElementById('base_method_textarea');
    const className = document.getElementById('class_name');

    if (!lob.value) {
        isValid = false;
        alert('Please select a Line Of Business.');
    }

    if (!builder.value) {
        isValid = false;
        alert('Please select a Builder.');
    }

    if (features.length === 0) {
        isValid = false;
        alert('Please select at least one Feature.');
    }

    if (gunitType.length === 0) {
        isValid = false;
        alert('Please select a Gunit Type.');
    }

    if (gunitType.length > 0) {
        if (gunitType[0].value === 'base_method' && !baseMethodTextarea.value.trim()) {
            isValid = false;
            alert('Please enter the Base Method.');
        }

        if (gunitType[0].value === 'class' && !className.value.trim()) {
            isValid = false;
            alert('Please enter the Class Name.');
        }
    }

    return isValid;
}
