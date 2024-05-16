console.log('main.js loaded');

// Selecting DOM elements
const gunitInput = document.getElementById('lob-input');
const output = document.getElementById('output');
const dropdownID=document.getElementById('lob_select')
const gunitForm=document.getElementById('gunit-input')
let uploadBtn; // Declaring uploadBtn variable

let gunitInputDisplayed = false;


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
    if (gunitInput && gunitForm ) {
        gunitInput.style.display = 'block';
        gunitForm.style.display = 'block';
        if (output) {
            output.style.display = 'none';
        }
        gunitInputDisplayed = true;
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


    uploadBtn = document.getElementById('upload-gunit');


    uploadBtn.addEventListener('click', (event) => {
        event.preventDefault();
        if (typeof initiateLoader === 'function') {
            initiateLoader();
        }
        document.querySelector('.upload-gunit').submit();
    });
});

